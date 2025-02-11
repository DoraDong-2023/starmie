#!/bin/sh

time python test_lsh.py \
    --encoder cl \
    --benchmark santos \
    --run_id 0 \
    --num_func 8 \
    --num_table 100 \
    --K 60 \
    --scal 1.0

