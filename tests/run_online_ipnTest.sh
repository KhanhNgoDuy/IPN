#!/bin/bash
export CUDA_VISIBLE_DEVICES=0

python online_test.py \
	--root_path host\
	--video_path IPN_dataset \
	--annotation_path annotation_ipnGesture/ipnall.json \
	--resume_path_det report_ipn/ipnDetRf_sc8b64_resnetl-10.pth \
	--resume_path_clf report_ipn/ipnClfRf_jes32rb32_resnext-101.pth \
	--result_path results_ipn \
	--dataset ipn \
	--store_name RGB-flo_l015Ma \
	--modality_det RGB-flo \
	--modality_clf RGB-flo \
	--sample_duration_det 8 \
	--sample_duration_clf 32 \
	--model_det resnetl \
	--model_clf resnext \
	--model_depth_det 10 \
	--model_depth_clf 101 \
	--resnet_shortcut_det A \
	--resnet_shortcut_clf B \
	--batch_size 1 \
	--n_classes_det 2 \
	--n_finetune_classes_det 2 \
	--n_classes_clf 13 \
	--n_finetune_classes_clf 13 \
	--n_threads 16 \
	--checkpoint 1 \
	--n_val_samples 1 \
	--train_crop random \
	--test_subset test  \
	--det_strategy ma \
	--det_queue_size 4 \
	--det_counter 2 \
	--clf_strategy ma \
	--clf_queue_size 16 \
	--clf_threshold_pre 0.15 \
	--clf_threshold_final 0.15 \
	--stride_len 1 \