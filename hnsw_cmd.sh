#!/bin/sh

# time python test_hnsw_search.py \
#     --encoder cl \
#     --benchmark santos \
#     --run_id 0 \
#     --K 60 \
#     --scal 1.0


time python test_hnsw_search.py \
    --encoder cl \
    --benchmark tus \
    --run_id 0 \
    --K 60 \
    --scal 1.0