#!/bin/sh

# santos small
python test_naive_search.py   --encoder cl   --benchmark santos   --augment_op drop_col   --sample_meth tfidf_entity   --matching linear   --table_order column   --run_id 0   --K 10   --threshold 0.7

# tus small
python test_naive_search.py   --encoder cl   --benchmark tus   --augment_op drop_cell  --sample_meth alphaHead  --matching linear   --table_order column   --run_id 0   --K 10   --threshold 0.7
