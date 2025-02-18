import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
import sklearn.metrics as metrics
import mlflow
import pandas as pd
import os
import matplotlib.pyplot as plt

from .utils import evaluate_column_matching, evaluate_clustering
from .model import BarlowTwinsSimCLR
from .dataset import PretrainTableDataset

from tqdm import tqdm
from torch.utils import data
from transformers import AdamW, get_linear_schedule_with_warmup
from typing import List

import warnings
warnings.filterwarnings("ignore")

def plot_curve(steps, step_train_losses, step_val_losses, log_scale=False):
    plt.figure(figsize=(8, 6))
    plt.plot(steps, step_train_losses, linestyle='-', color='b', label="Training Loss")
    if len(step_val_losses)>0:
        plt.plot(steps, step_val_losses, linestyle='-', color='r', label="Validation Loss")
    plt.xlabel("Step")
    plt.ylabel("Loss")
    if log_scale:
        plt.yscale("log")
    plt.legend()
    plt.title("Starmie Loss")
    plt.grid(True)
    # Save the figure
    plot_path = "./final_loss_plot.pdf"
    plt.savefig(plot_path)
    plt.show()

def train_step(train_iter, val_iter, model, optimizer, scheduler, scaler, hp, step_train_losses, step_val_losses, global_step, steps):
    """Perform a single training step

    Args:
        train_iter (Iterator): the train data loader
        model (BarlowTwinsSimCLR): the model
        optimizer (Optimizer): the optimizer (Adam or AdamW)
        scheduler (LRScheduler): learning rate scheduler
        scaler (GradScaler): gradient scaler for fp16 training
        hp (Namespace): other hyper-parameters (e.g., fp16)

    Returns:
        None
    """
    model.train()
    for i, batch in enumerate(train_iter):
        x_ori, x_aug, cls_indices = batch
        optimizer.zero_grad()
        if hp.fp16:
            with torch.cuda.amp.autocast():
                loss = model(x_ori, x_aug, cls_indices, mode='simclr')
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
        else:
            loss = model(x_ori, x_aug, cls_indices, mode='simclr')
            loss.backward()
            optimizer.step()
        scheduler.step()
        global_step += 1

        if i % 10 == 0: # monitoring
            step_train_losses.append(loss.item())
            steps.append(global_step)
            if val_iter:
                model.eval()
                with torch.no_grad():
                    val_batch = next(iter(val_iter))  # Take one batch from val_loader
                    x_val_ori, x_val_aug, val_cls_indices = val_batch
                    val_loss = model(x_val_ori, x_val_aug, val_cls_indices, mode='simclr')
                    step_val_losses.append(val_loss.item())  # Store validation loss
            print(f"Step {global_step}: Train Loss = {loss.item():.4f}, Val Loss = {val_loss.item():.4f}" if val_iter else f"Step {global_step}: Train Loss = {loss.item():.4f}")
        del loss
    return step_train_losses, step_val_losses, global_step, steps


def train(trainset, hp, valset=None):
    """Train and evaluate the model

    Args:
        trainset (PretrainTableDataset): the training set
        hp (Namespace): Hyper-parameters (e.g., batch_size,
                        learning rate, fp16)
    Returns:
        The pre-trained table model
    """
    padder = trainset.pad
    # create the DataLoaders
    train_iter = data.DataLoader(dataset=trainset,
                                 batch_size=hp.batch_size,
                                 shuffle=True,
                                 num_workers=0,
                                 collate_fn=padder)
    val_iter = data.DataLoader(dataset=valset,
                                   batch_size=hp.batch_size,
                                   shuffle=False,
                                   num_workers=0,
                                   collate_fn=padder) if valset else None

    # initialize model, optimizer, and LR scheduler
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = BarlowTwinsSimCLR(hp, device=device, lm=hp.lm)
    if device=='cuda':
        model = model.cuda()
    optimizer = AdamW(model.parameters(), lr=hp.lr)
    if device=='cuda' and hp.fp16:
        scaler = torch.cuda.amp.GradScaler()
    else:
        scaler = None
    num_steps = (len(trainset) // hp.batch_size) * hp.n_epochs
    scheduler = get_linear_schedule_with_warmup(optimizer,
                                                num_warmup_steps=0,
                                                num_training_steps=num_steps)
    step_train_losses = []
    step_val_losses = []
    steps = []
    global_step = 0
    for epoch in range(1, hp.n_epochs+1):
        # train
        step_train_losses, step_val_losses, global_step, steps = train_step(train_iter, val_iter, model, optimizer, scheduler, scaler, hp, step_train_losses, step_val_losses, global_step, steps)
        # save the last checkpoint
        if hp.save_model and epoch == hp.n_epochs:
            directory = os.path.join(hp.logdir, hp.task)
            if not os.path.exists(directory):
                os.makedirs(directory)
            # save the checkpoints for each component
            if hp.single_column:
                ckpt_path = os.path.join(hp.logdir, hp.task, 'model_'+str(hp.augment_op)+'_'+str(hp.sample_meth)+'_'+str(hp.table_order)+'_'+str(hp.run_id)+'singleCol.pt')
            else:
                ckpt_path = os.path.join(hp.logdir, hp.task, 'model_'+str(hp.augment_op)+'_'+str(hp.sample_meth)+'_'+str(hp.table_order)+'_'+str(hp.run_id)+'.pt')
            ckpt = {'model': model.state_dict(),
                    'hp': hp}
            torch.save(ckpt, ckpt_path)
            # test loading checkpoints
            # load_checkpoint(ckpt_path)
        # intrinsic evaluation with column matching
        if hp.task in ['small', 'large']:
            # Train column matching models using the learned representations
            metrics_dict = evaluate_pretrain(model, trainset)
            # log metrics
            mlflow.log_metrics(metrics_dict)
            print("epoch %d: " % epoch + ", ".join(["%s=%f" % (k, v) \
                                    for k, v in metrics_dict.items()]))
        # evaluate on column clustering
        if hp.task in ['viznet']:
            # Train column matching models using the learned representations
            metrics_dict = evaluate_column_clustering(model, trainset)
            # log metrics
            mlflow.log_metrics(metrics_dict)
            print("epoch %d: " % epoch + ", ".join(["%s=%f" % (k, v) \
                                    for k, v in metrics_dict.items()]))
    save_losses_as_csv(steps, step_train_losses, step_val_losses)
    plot_curve(steps, step_train_losses, step_val_losses)

def save_losses_as_csv(steps, train_losses, val_losses, filename="loss_data.csv"):
    df = pd.DataFrame({"Step": steps, "Train Loss": train_losses, "Validation Loss": val_losses})
    df.to_csv(filename, index=False)
    print(f"Loss data saved to {filename}")

def validation_step(val_loader, model, hp):
    total_loss = []
    model.eval()
    with torch.no_grad():
        for batch in val_loader:
            x_ori, x_aug, cls_indices = batch
            loss = model(x_ori, x_aug, cls_indices, mode='simclr')
            total_loss.append(loss.item())
    return total_loss

def inference_on_tables(tables: List[pd.DataFrame],
                        model: BarlowTwinsSimCLR,
                        unlabeled: PretrainTableDataset,
                        batch_size=128,
                        total=None):
    """Extract column vectors from a table.

    Args:
        tables (List of DataFrame): the list of tables
        model (BarlowTwinsSimCLR): the model to be evaluated
        unlabeled (PretrainTableDataset): the unlabeled dataset
        batch_size (optional): batch size for model inference

    Returns:
        List of np.array: the column vectors
    """
    total=total if total is not None else len(tables)
    batch = []
    results = []
    for tid, table in tqdm(enumerate(tables), total=total):
        x, _ = unlabeled._tokenize(table)

        batch.append((x, x, []))
        if tid == total - 1 or len(batch) == batch_size:
            # model inference
            with torch.no_grad():
                x, _, _ = unlabeled.pad(batch)
                # all column vectors in the batch
                column_vectors = model.inference(x)
                ptr = 0
                for xi in x:
                    current = []
                    for token_id in xi:
                        if token_id == unlabeled.tokenizer.cls_token_id:
                            current.append(column_vectors[ptr].cpu().numpy())
                            ptr += 1
                    results.append(current)

            batch.clear()

    return results


def load_checkpoint(ckpt):
    """Load a model from a checkpoint.
        ** If you would like to run your own benchmark, update the ds_path here
    Args:
        ckpt (str): the model checkpoint.

    Returns:
        BarlowTwinsSimCLR: the pre-trained model
        PretrainDataset: the dataset for pre-training the model
    """
    hp = ckpt['hp']

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(device)
    model = BarlowTwinsSimCLR(hp, device=device, lm=hp.lm)
    model = model.to(device)
    model.load_state_dict(ckpt['model'])

    # dataset paths, depending on benchmark for the current task
    ds_path = 'data/santos/datalake'
    if hp.task == "santosLarge":
        # Change the data paths to where the benchmarks are stored
        ds_path = 'data/santos-benchmark/real-benchmark/datalake'
    elif hp.task == "tus":
        ds_path = 'data/table-union-search-benchmark/small/benchmark'
    elif hp.task == "tusLarge":
        ds_path = 'data/table-union-search-benchmark/large/benchmark'
    elif hp.task == "wdc":
        ds_path = 'data/wdc/0'
    dataset = PretrainTableDataset.from_hp(ds_path, hp)

    return model, dataset


def evaluate_pretrain(model: BarlowTwinsSimCLR,
                      unlabeled: PretrainTableDataset):
    """Evaluate pre-trained model.

    Args:
        model (BarlowTwinsSimCLR): the model to be evaluated
        unlabeled (PretrainTableDataset): the unlabeled dataset

    Returns:
        Dict: the dictionary of metrics (e.g., valid_f1)
    """
    table_path = 'data/%s/tables' % model.hp.task

    # encode each dataset
    featurized_datasets = []
    for dataset in ["train", "valid", "test"]:
        ds_path = 'data/%s/%s.csv' % (model.hp.task, dataset)
        ds = pd.read_csv(ds_path)

        def encode_tables(table_ids, column_ids):
            tables = []
            for table_id, col_id in zip(table_ids, column_ids):
                table = pd.read_csv(os.path.join(table_path, \
                                    "table_%d.csv" % table_id))
                if model.hp.single_column:
                    table = table[[table.columns[col_id]]]
                tables.append(table)
            vectors = inference_on_tables(tables, model, unlabeled,
                                          batch_size=128)

            # assert all columns exist
            for vec, table in zip(vectors, tables):
                assert len(vec) == len(table.columns)

            res = []
            for vec, cid in zip(vectors, column_ids):
                if cid < len(vec):
                    res.append(vec[cid])
                else:
                    # single column
                    res.append(vec[-1])
            return res

        # left tables
        l_features = encode_tables(ds['l_table_id'], ds['l_column_id'])

        # right tables
        r_features = encode_tables(ds['r_table_id'], ds['r_column_id'])

        features = []
        Y = ds['match']
        for l, r in zip(l_features, r_features):
            feat = np.concatenate((l, r, np.abs(l - r)))
            features.append(feat)

        featurized_datasets.append((features, Y))

    train, valid, test = featurized_datasets
    return evaluate_column_matching(train, valid, test)


def evaluate_column_clustering(model: BarlowTwinsSimCLR,
                               unlabeled: PretrainTableDataset):
    """Evaluate pre-trained model on a column clustering dataset.

    Args:
        model (BarlowTwinsSimCLR): the model to be evaluated
        unlabeled (PretrainTableDataset): the unlabeled dataset

    Returns:
        Dict: the dictionary of metrics (e.g., purity, number of clusters)
    """
    table_path = 'data/%s/tables' % model.hp.task

    # encode each dataset
    featurized_datasets = []
    ds_path = 'data/%s/test.csv' % model.hp.task
    ds = pd.read_csv(ds_path)
    table_ids, column_ids = ds['table_id'], ds['column_id']

    # encode all tables
    def table_iter():
        for table_id, col_id in zip(table_ids, column_ids):
            table = pd.read_csv(os.path.join(table_path, \
                                "table_%d.csv" % table_id))
            if model.hp.single_column:
                table = table[[table.columns[col_id]]]
            yield table

    vectors = inference_on_tables(table_iter(), model, unlabeled,
                                    batch_size=128, total=len(table_ids))

    # # assert all columns exist
    # for vec, table in zip(vectors, tables):
    #     assert len(vec) == len(table.columns)

    column_vectors = []
    for vec, cid in zip(vectors, column_ids):
        if cid < len(vec):
            column_vectors.append(vec[cid])
        else:
            # single column
            column_vectors.append(vec[-1])

    return evaluate_clustering(column_vectors, ds['class'])

def load_and_read_csv(filename="loss_data.csv", num_rows=10):
    """Load and display the first few rows of the saved loss data CSV."""
    try:
        df = pd.read_csv(filename)
        print(f"Loaded CSV from {filename}")
        print(df.head(num_rows))  # Show the first few rows
        return df
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return None

if __name__=='main':
    # test mode
    df = load_and_read_csv("loss_data.csv")
    print(df)
    plot_curve(df['steps'], df['train_losses'], df['val_losses'], log_scale=True)
    