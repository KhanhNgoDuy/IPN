#!/bin/bash 	#dl04
python main.py \
	--root_path /host/space0/gibran/\
	--video_path dataset/HandGestures/IPN_dataset \
	--annotation_path scripts/Real-time-GesRec/annotation_ipnGesture/ipnall_but_None_seg.json \
	--result_path scripts/Real-time-GesRec/results_ipn \
	--pretrain_path scripts/Real-time-GesRec/report/jester_resnext_101_RGB_32.pth \
	--pretrain_dataset jester \
	--dataset ipn \
	--sample_duration 32 \
    --learning_rate 0.01 \
    --model resnext \
	--model_depth 101 \
	--resnet_shortcut B \
	--batch_size 32 \
	--n_classes 13 \
	--n_finetune_classes 13 \
	--n_threads 16 \
	--checkpoint 1 \
	--modality RGB-seg \
	--train_crop random \
	--n_val_samples 1 \
	--test_subset test \
    --n_epochs 100 \
    --store_name ipnClfRs_jes32r_b32 \