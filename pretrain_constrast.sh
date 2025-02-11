#!/bin/bash
#SBATCH --job-name=myjob     
#SBATCH --gres=gpu:1         
#SBATCH --cpus-per-task=4    
#SBATCH --mem=16G            
#SBATCH --time=4:00:00       
#SBATCH -o output.log        
#SBATCH -e error.log         

# echo "1/4 Training Santos"
# CUDA_VISIBLE_DEVICES=0 python run_pretrain.py \
#   --task santos \
#   --batch_size 64 \
#   --lr 5e-5 \
#   --lm roberta \
#   --n_epochs 10 \
#   --max_len 128 \
#   --projector 768 \
#   --save_model \
#   --table_order column \
#   --augment_op drop_col \
#   --sample_meth tfidf_entity \
#   --fp16 \
#   --run_id 0

# echo "2/4 Training SantosLarge"
# CUDA_VISIBLE_DEVICES=0 python run_pretrain.py \
#   --task santosLarge \
#   --batch_size 64 \
#   --lr 5e-5 \
#   --lm roberta \
#   --n_epochs 10 \
#   --max_len 128 \
#   --projector 768 \
#   --save_model \
#   --table_order column \
#   --augment_op drop_col \
#   --sample_meth tfidf_entity \
#   --fp16 \
#   --run_id 0

# echo "3/4 Training TUS"
# CUDA_VISIBLE_DEVICES=0 python run_pretrain.py \
#   --task tus \
#   --batch_size 64 \
#   --lr 5e-5 \
#   --lm roberta \
#   --n_epochs 10 \
#   --max_len 128 \
#   --projector 768 \
#   --save_model \
#   --table_order column \
#   --augment_op drop_cell \
#   --sample_meth alphaHead \
#   --fp16 \
#   --run_id 0

# echo "4/4 Training TUS Large"
# CUDA_VISIBLE_DEVICES=0 python run_pretrain.py \
#   --task tusLarge \
#   --batch_size 64 \
#   --lr 5e-5 \
#   --lm roberta \
#   --n_epochs 10 \
#   --max_len 128 \
#   --projector 768 \
#   --save_model \
#   --table_order column \
#   --augment_op drop_cell \
#   --sample_meth tfidf_entity \
#   --fp16 \
#   --run_id 0
