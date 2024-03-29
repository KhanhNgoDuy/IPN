import argparse
import time
import os
import glob 
import sys
import json
import shutil
import itertools
from unittest import skip
import numpy as np
import pandas as pd 
import csv
import torch
from torch.autograd import Variable
from sklearn.metrics import confusion_matrix
from torch.nn import functional as F

from opts import parse_opts_online
from model import generate_model, _modify_first_conv_layer, _construct_depth_model
from mean import get_mean, get_std
from spatial_transforms import *
from temporal_transforms import *
# from temporal_transforms_adap import *
from target_transforms import ClassLabel
from dataset import get_online_data 
from utils import Logger, AverageMeter, LevenshteinDistance, Queue

import pdb
import numpy as np

import matplotlib.pyplot as plt
from matplotlib.pyplot import figure
import scipy.io as sio


def plot_(clf_):
    print('Testing plot')
    x = np.arange(len(clf_))
    plt.plot(x, clf_)
    plt.show()


def plot_result(det, clf):
    print(f'det.shape {len(det)}')
    print(f'clf.shape {clf.shape}')
    
    plt.figure(1)
    x = np.arange(len(det))
    det = np.array(det)
    plt.plot(x, det)
    
    plt.figure(2)
    x = np.arange(clf.shape[0])
    clf = np.array(clf)
    plt.plot(x, clf)
    
    plt.show()
    

def weighting_func(x):
    return (1 / (1 + np.exp(-0.2*(x-9))))


opt = parse_opts_online()

def load_models(opt):
    opt.resume_path = opt.resume_path_det
    opt.pretrain_path = opt.pretrain_path_det
    opt.sample_duration = opt.sample_duration_det
    opt.model = opt.model_det
    opt.model_depth = opt.model_depth_det
    opt.modality = opt.modality_det
    opt.resnet_shortcut = opt.resnet_shortcut_det
    opt.n_classes = opt.n_classes_det
    opt.n_finetune_classes = opt.n_finetune_classes_det
    opt.no_first_lay = opt.no_first_lay_det

    if opt.root_path != '':
        opt.video_path = os.path.join(opt.root_path, opt.video_path)
        opt.annotation_path = os.path.join(opt.root_path, opt.annotation_path)
        opt.result_path = os.path.join(opt.root_path, opt.result_path)
        if opt.resume_path:
            opt.resume_path = os.path.join(opt.root_path, opt.resume_path)
        if opt.pretrain_path:
            opt.pretrain_path = os.path.join(opt.root_path, opt.pretrain_path)


    opt.scales = [opt.initial_scale]
    for i in range(1, opt.n_scales):
        opt.scales.append(opt.scales[-1] * opt.scale_step)
    opt.arch = '{}-{}'.format(opt.model, opt.model_depth)
    opt.mean = get_mean(opt.norm_value)
    opt.std = get_std(opt.norm_value)

    print(opt)
    with open(os.path.join(opt.result_path, 'opts_det_{}.json'.format(opt.store_name)), 'w') as opt_file:
        json.dump(vars(opt), opt_file)

    torch.manual_seed(opt.manual_seed)

    detector, parameters = generate_model(opt)

    if opt.resume_path:
        #opt.resume_path = os.path.join(opt.root_path, opt.resume_path)
        print('loading checkpoint {}'.format(opt.resume_path))
        checkpoint = torch.load(opt.resume_path)
        assert opt.arch == checkpoint['arch']

        detector.load_state_dict(checkpoint['state_dict'])

    #print('Model 1 \n', detector)
    pytorch_total_params = sum(p.numel() for p in detector.parameters() if
                               p.requires_grad)
    #print("Total number of trainable parameters: ", pytorch_total_params)


    opt.resume_path = opt.resume_path_clf
    opt.pretrain_path = opt.pretrain_path_clf
    opt.sample_duration = opt.sample_duration_clf
    opt.model = opt.model_clf
    opt.model_depth = opt.model_depth_clf
    opt.modality = opt.modality_clf
    opt.resnet_shortcut = opt.resnet_shortcut_clf
    opt.n_classes = opt.n_classes_clf
    opt.n_finetune_classes = opt.n_finetune_classes_clf
    opt.no_first_lay = opt.no_first_lay_clf

    if opt.root_path != '':
        #opt.video_path = os.path.join(opt.root_path, opt.video_path)
        #opt.annotation_path = os.path.join(opt.root_path, opt.annotation_path)
        #opt.result_path = os.path.join(opt.root_path, opt.result_path)
        if opt.resume_path:
            opt.resume_path = os.path.join(opt.root_path, opt.resume_path)
        if opt.pretrain_path:
            opt.pretrain_path = os.path.join(opt.root_path, opt.pretrain_path)

    opt.scales = [opt.initial_scale]
    for i in range(1, opt.n_scales):
        opt.scales.append(opt.scales[-1] * opt.scale_step)
    opt.arch = '{}-{}'.format(opt.model, opt.model_depth)
    opt.mean = get_mean(opt.norm_value)
    opt.std = get_std(opt.norm_value)

    print(opt)
    with open(os.path.join(opt.result_path, 'opts_clf_{}.json'.format(opt.store_name)), 'w') as opt_file:
        json.dump(vars(opt), opt_file)

    torch.manual_seed(opt.manual_seed)
    classifier, parameters = generate_model(opt)

    if opt.resume_path:
        print('loading checkpoint {}'.format(opt.resume_path))
        checkpoint = torch.load(opt.resume_path)
        assert opt.arch == checkpoint['arch']
        if opt.sample_duration_clf < 32 and opt.model_clf != 'c3d':
            classifier = _modify_first_conv_layer(classifier,3,3)
            classifier = _construct_depth_model(classifier)
            classifier = classifier.cuda()
        classifier.load_state_dict(checkpoint['state_dict'])

    #print('Model 2 \n', classifier)
    pytorch_total_params = sum(p.numel() for p in classifier.parameters() if
                               p.requires_grad)
    #print("Total number of trainable parameters: ", pytorch_total_params)

    return detector, classifier

opt.store_name = '{}_{}_{}'.format(opt.store_name, opt.test_subset, opt.model_clf)
detector,classifier = load_models(opt)
sys.stdout.flush()

if opt.no_mean_norm and not opt.std_norm:
    norm_method = Normalize([0, 0, 0], [1, 1, 1])
elif not opt.std_norm:
    norm_method = Normalize(opt.mean, [1, 1, 1])
else:
    norm_method = Normalize(opt.mean, opt.std)


spatial_transform = Compose([
    Scale(112),
    CenterCrop(112),
    ToTensor(opt.norm_value), norm_method
    ])

target_transform = ClassLabel()

with open('checkpoint.txt', 'r') as f:
    checkpoint = f.read()
    print(f'Checkpoint: {checkpoint}')

## Get list of videos to test
if opt.dataset == 'ipn':
    file_set = os.path.join(opt.video_path, 'Video_TestList.txt')
    test_paths = []
    buf = int(checkpoint)
    video_count = int(checkpoint)
    with open(file_set,'rb') as f:
        for line in f:
            vid_name = line.decode().split('\t')[0]
            test_paths.append(os.path.join(opt.video_path, 'frames', vid_name))


print('Start Evaluation')
detector.eval()
classifier.eval()

detector_accuracies = AverageMeter()
levenshtein_accuracies = AverageMeter()
det_idxs = []
end_frames = []
pre_classes = []
all_pred_frames = []
all_pred_starts = []
all_pred = []
all_true_frames = []
all_true_starts = []
all_true = []
videoidx = 0
videopath = []

early = 0
late = 0
none = 0

for idx, path in enumerate(test_paths[buf:]):
    video_count = video_count + 1
    
    if opt.dataset == 'egogesture':
        opt.whole_path = path.split(os.sep, 4)[-1]
    elif opt.dataset == 'nv':
        opt.whole_path = path.split(os.sep, 7)[-1]
    elif opt.dataset == 'ipn':
        opt.whole_path = os.path.join('frames', path.split(os.sep)[-1])  
    elif opt.dataset == 'AHG':
        opt.whole_path = path
    elif opt.dataset == 'denso':
        opt.whole_path = path
    
    videoidx += 1
    active_index = 0
    passive_count = 0
    active = False
    prev_active = False
    finished_prediction = None
    pre_predict = False

    cum_sum = np.zeros(opt.n_classes_clf,)
    clf_selected_queue = np.zeros(opt.n_classes_clf,)
    det_selected_queue = np.zeros(opt.n_classes_det,)
    myqueue_det = Queue(opt.det_queue_size ,  n_classes = opt.n_classes_det)
    myqueue_clf = Queue(opt.clf_queue_size, n_classes = opt.n_classes_clf )


    print('[{}/{}]============'.format(videoidx,len(test_paths)))
    print(path)
    sys.stdout.flush()
    opt.sample_duration = max(opt.sample_duration_clf, opt.sample_duration_det)
    test_data = get_online_data(
        opt, spatial_transform, None, target_transform)

    test_loader = torch.utils.data.DataLoader(
                test_data,
                batch_size=opt.batch_size,
                shuffle=False,
                num_workers=opt.n_threads,
                pin_memory=True)


    results = []
    pred_frames = []
    pred_start = []
    pred_starts = []
    prev_best1 = opt.n_classes_clf
    det_idx = np.zeros(6000)
    end_fra = np.zeros(1000)
    pre_cla = np.zeros(1000)
    det_idx[0] = test_data.data[-1]['frame_indices'][-1]
    
    #Begin  #Added
    DET_THRESHOLD = 0.8
    total_frame = int(det_idx[0] + 1)
    total_true = 0
    total_pred = 0
    P_frame = np.random.rand(total_frame)
    T_frame = np.random.rand(total_frame)
    det = []
    clf = []
    clf_ = np.zeros(total_frame)
    best = []
    #End

    for i, (inputs, targets) in enumerate(test_loader):
        if not opt.no_cuda:
            targets = targets.cuda(non_blocking=True)
        ground_truth_array = np.zeros(opt.n_classes_clf +1,)
        with torch.no_grad():
            inputs = Variable(inputs)
            targets = Variable(targets)
            if opt.modality_det in ['RGB', 'RGB-D', 'RGB-flo', 'RGB-seg']:
                inputs_det = inputs[:,:,-opt.sample_duration_det:,:,:]
            elif opt.modality_det == 'Depth':
                inputs_det = inputs[:,-1,-opt.sample_duration_det:,:,:].unsqueeze(1)
            
            s_dt = time.time()
            # pdb.set_trace()
            outputs_det = detector(inputs_det)
            outputs_det = F.softmax(outputs_det,dim=1)
            outputs_det = outputs_det.cpu().numpy()[0].reshape(-1,)
            e_dt = time.time()

            # enqueue the probabilities to the detector queue
            myqueue_det.enqueue(outputs_det.tolist())

            if opt.det_strategy == 'raw':
                det_selected_queue = outputs_det
            elif opt.det_strategy == 'median':
                det_selected_queue = myqueue_det.median
            elif opt.det_strategy == 'ma':
                det_selected_queue = myqueue_det.ma
            elif opt.det_strategy == 'ewma':
                det_selected_queue = myqueue_det.ewma
            
            prediction_det = np.argmax(det_selected_queue)
            prob_det = det_selected_queue[prediction_det]
            
            #### State of the detector is checked here as detector act as a switch for the classifier
            if  prediction_det == 1:
                #print("test_data.data[i]['frame_indices'][-1]: ",test_data.data[i]['frame_indices'][-1])
                  # det_idx[i] = test_data.data[i]['frame_indices'][-1]
                det_idx[test_data.data[i]['frame_indices'][-1]] = 1
                pred_start.append(test_data.data[i]['frame_indices'][-1])
                if opt.modality_clf in ['RGB', 'RGB-D', 'RGB-flo', 'RGB-seg']:
                    inputs_clf = inputs[:,:,:,:,:]
                elif opt.modality_clf == 'Depth':
                    inputs_clf = inputs[:,-1,:,:,:].unsqueeze(1)

                s_ct = time.time()
                outputs_clf = classifier(inputs_clf)
                outputs_clf = F.softmax(outputs_clf,dim=1)
                outputs_clf = outputs_clf.cpu().numpy()[0].reshape(-1,)
                e_ct = time.time()
                
                # Push the probabilities to queue
                myqueue_clf.enqueue(outputs_clf.tolist())
                passive_count = 0

                if opt.clf_strategy == 'raw':
                    clf_selected_queue = outputs_clf
                elif opt.clf_strategy == 'median':
                    clf_selected_queue = myqueue_clf.median
                elif opt.clf_strategy == 'ma':
                    clf_selected_queue = myqueue_clf.ma
                elif opt.clf_strategy == 'ewma':
                    clf_selected_queue = myqueue_clf.ewma
                    
                det.extend([1])
                clf.extend([outputs_clf.argmax() + 1])
                    
            else:
                print('No gesture at frame ', test_data.data[i]['frame_indices'][-1])
                det.extend([0])
                clf.extend([0])
                outputs_clf = np.zeros(opt.n_classes_clf ,)
                # Push the probabilities to queue
                myqueue_clf.enqueue(outputs_clf.tolist())
                passive_count += 1
        
        

        if passive_count >= opt.det_counter:
            active = False
        else:
            active = True

        # one of the following line need to be commented !!!!
        if active:
            active_index += 1
            cum_sum = ((cum_sum * (active_index-1)) + (weighting_func(active_index) * clf_selected_queue))/active_index # Weighted Aproach
            # cum_sum = ((cum_sum * (x-1)) + (1.0 * clf_selected_queue))/x #Not Weighting Aproach 

            best2, best1 = tuple(cum_sum.argsort()[-2:][::1])
            if float(cum_sum[best1]- cum_sum[best2]) > opt.clf_threshold_pre:
                finished_prediction = True
                pre_predict = True
            
        else:
            active_index = 0


        if active == False and  prev_active == True:
            finished_prediction = True
        elif active == True and  prev_active == False:
            finished_prediction = False

        if test_data.data[i]['frame_indices'][-1] % 500 == 0:
            #print('No gestures detected at frame {}'.format(test_data.data[i]['frame_indices'][-1]))
            sys.stdout.flush()
        
        if finished_prediction == True:
            best2, best1 = tuple(cum_sum.argsort()[-2:][::1])
            if cum_sum[best1]>opt.clf_threshold_final:
                if pre_predict == True:  
                    if best1 != prev_best1:
                        if cum_sum[best1]>opt.clf_threshold_final:  
                            results.append(((i*opt.stride_len)+opt.sample_duration_clf,best1))
                            videopath.append('.' + path[16:])       #Add
                            #print( 'Early Detected - class : {} with prob : {} at frames {}~{}'.format(best1, cum_sum[best1], pred_start[0], test_data.data[i]['frame_indices'][-1]))
                            pred_frames.append(test_data.data[i]['frame_indices'][-1])
                            pred_starts.append(pred_start[0])
                            pred_start = []
                            best.append(best1 + 1)
                else:
                    if cum_sum[best1]>opt.clf_threshold_final:
                        if best1 == prev_best1:
                            if cum_sum[best1]>5:    #????????
                                results.append(((i*opt.stride_len)+opt.sample_duration_clf,best1))
                                videopath.append('.' + path[16:])       #Add
                                #print( 'Late Detected - class : {} with prob : {} at frames {}~{}'.format(best1, cum_sum[best1], pred_start[0], test_data.data[i]['frame_indices'][-1]))
                                pred_frames.append(test_data.data[i]['frame_indices'][-1])
                                pred_starts.append(pred_start[0])
                                pred_start = []
                                best.append(best1 + 1)
                        else:
                            results.append(((i*opt.stride_len)+opt.sample_duration_clf,best1))
                            videopath.append('.' + path[16:])       #Add
                            #print( 'Late Detected - class : {} with prob : {} at frames {}~{}'.format(best1, cum_sum[best1], pred_start[0], test_data.data[i]['frame_indices'][-1]))
                            pred_frames.append(test_data.data[i]['frame_indices'][-1])
                            pred_starts.append(pred_start[0])
                            pred_start = []
                            best.append(best1 + 1)
                
                finished_prediction = False
                prev_best1 = best1
                pred_start = []

            cum_sum = np.zeros(opt.n_classes_clf,)
            pred_start = []
            sys.stdout.flush()

        if active == False and  prev_active == True:
            pre_predict = False
    
        prev_active = active
    
    #Begin    #Added
    
    for start, end, class_ in zip(pred_starts, pred_frames, best):
        P_frame[start - 1 : end] = [1 for _ in range(start - 1, end)]
        clf_[start - 1 : end] = class_

    if opt.dataset == 'egogesture':
        target_csv_path = os.path.join(opt.video_path.rsplit(os.sep, 1)[0], 
                                'labels-final-revised1',
                                opt.whole_path.rsplit(os.sep,2)[0],
                                'Group'+opt.whole_path[-1] + '.csv').replace('Subject', 'subject')
        true_classes = []
        with open(target_csv_path) as csvfile:
            readCSV = csv.reader(csvfile, delimiter=',')
            for row in readCSV:
                true_classes.append(int(row[0])-1)

    if opt.dataset == 'ipn':
        true_classes = []
        true_frames = []
        true_starts = []
        detector_accuracy = 0
        
        with open('host/annotation_ipnGesture/vallistall.txt') as csvfile:
            readCSV = csv.reader(csvfile, delimiter=' ')
            for row in readCSV:
                if row[0][2:] == opt.whole_path:
                    if row[1] != '1' :
                        true_classes.append(int(row[1])-2)
                        true_starts.append(int(row[2]))
                        true_frames.append(int(row[3]))
                        
	          #Beginning #Added
                        start = true_starts[-1]
                        end = true_frames[-1]
                        frame_count = end - start + 1 
                        T_frame[start-1 : end] = 1          

                        correct_detected = np.sum(T_frame == P_frame)
                        
                        det_gap = 0
                        for x in P_frame[start-1 : end]:
                            if x != 1:
                                det_gap += 1
                            else: 
                                break
                        
                        temp = 1 - (det_gap/frame_count)
                        if temp < DET_THRESHOLD and temp > 0:
                            #print(f'Late detected with IoU {correct_detected}/{frame_count} at frames {start}~{end}')
                            late += 1
                        elif temp > DET_THRESHOLD:
                            #print(f'Early detected with IoU {correct_detected}/{frame_count} at frames {start}~{end}')
                            early += 1
                        elif temp == 0:
                            #print(f'No gesture at frames {start}~{end}')
                            none += 1
                                                      
                        total_pred += correct_detected
                        total_true += frame_count
                        
                        T_frame = np.random.rand(total_frame)

    detector_accuracy = total_pred/total_true
    detector_accuracies.update(detector_accuracy)
    print(f'Detector accuracy = {detector_accuracies.val} ({detector_accuracies.avg})')
    print(f'{total_pred}/{total_true}')
    print(f'Early detected: {early: }\nLate detected: {late: }\nNone: {none: }')
	#Ending
         
                          
    true_classes = np.array(true_classes)
    if results == []:
        predicted = np.array(results)
        pred_frames = np.array(pred_frames)
        levenshtein_distance = -1
    else:
        pred_frames = np.array(pred_frames)
        predicted = np.array(results)[:,1]
        levenshtein_distance = LevenshteinDistance(true_classes, predicted)
        # pdb.set_trace()
        levenshtein_accuracy = 1-(levenshtein_distance/len(true_classes))
        pre_cla[0:len(predicted)] = predicted+1
        end_fra[0:len(pred_frames)] = pred_frames

    if levenshtein_distance <0: # Distance cannot be less than 0
        levenshtein_accuracies.update(0, len(true_classes))
        # pass
    else:
        levenshtein_accuracies.update(levenshtein_accuracy, len(true_classes))

    pred = []
    all_pred.append(predicted.tolist())
    all_pred_frames.append(pred_frames.tolist())
    all_pred_starts.append(pred_starts)
    for i, pn in enumerate(predicted):
        pred.append('{}({}~{})'.format(pn, pred_starts[i], pred_frames[i]))
    true_gt = []
    all_true.append(true_classes.tolist())
    all_true_frames.append(true_frames)
    all_true_starts.append(true_starts)
    for i, pn in enumerate(true_classes):
        true_gt.append('{}({}~{})'.format(pn, true_starts[i], true_frames[i]))
    # print('predicted classes: \t {} \t at frames: {}'.format(predicted, pred_frames))
    # print('True classes :\t\t {} \t at frames: {}'.format(true_classes, true_frames))
    if results == []:
        print('predicted classes:  {}'.format('NONE'))
    else:
        print('predicted classes:  {}'.format(' '.join(pred)))
    print('True classes :\t {}'.format(' '.join(true_gt)))
    print('Levenshtein Accuracy = {} ({}) frame detections: {}/{}'.format(
    	levenshtein_accuracies.val, 
    	levenshtein_accuracies.avg, 
    	np.sum(det_idx[2:]), det_idx[0]),
    )
    det_idxs.append(det_idx)
    end_frames.append(end_fra)
    pre_classes.append(pre_cla)
    sys.stdout.flush()
    #plot_result(det, clf_)
    
    #Begin
    with open('val_pred_clf.txt', 'a') as f:
        for i in range(len(videopath)):
            print(f'Length of video path: {len(videopath)}')
            f.write(f'{videopath[i]} {best[i]} {pred_starts[i]} {pred_frames[i]}\n')
            
    with open('val_pred_det.txt', 'a') as f:
        f.write(videopath[0] + '\n')
        f.write(' '.join(str(item) for item in clf))
        f.write('\n')
        print('End of val_pred_det.txt')
    
    with open('checkpoint.txt', 'w') as f:
        f.write(str(video_count))
    
    videopath = []
    best = []
    #End
    
print('Average Levenshtein Accuracy= {}'.format(levenshtein_accuracies.avg))

print('-----Evaluation is finished------')
res_data = {}
res_data['all_pred'] = all_pred
res_data['all_pred_frames'] = all_pred_frames
res_data['all_pred_starts'] = all_pred_starts
res_data['all_true'] = all_true
res_data['all_true_frames'] = all_true_frames
res_data['all_true_starts'] = all_true_starts
with open(os.path.join(opt.result_path,'res_'+opt.store_name+'.json'), 'w') as dst_file:
    json.dump(res_data, dst_file)
# det_idxs = np.array(det_idxs)
# end_frames = np.array(end_frames)
# pre_classes = np.array(pre_classes)
# sio.savemat(os.path.join(opt.result_path,opt.store_name+'.mat'), {'detecs':det_idxs, 'efs':end_frames, 'p_id':pre_classes})
