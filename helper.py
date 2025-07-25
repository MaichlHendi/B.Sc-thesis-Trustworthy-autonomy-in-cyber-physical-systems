import sys
import os
import time
import math
import torch
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from torch.autograd import Variable
from utils.utils import non_max_suppression
import copy
import struct # get_image_size
import imghdr # get_image_size

def sigmoid(x):
    return 1.0/(math.exp(-x)+1.)

def softmax(x):
    x = torch.exp(x - torch.max(x))
    x = x/x.sum()
    return x


def bbox_iou(box1, box2, x1y1x2y2=True, verbose=False, objsk=0, int_only=False, match_class=False):
    #if len(box1[:4]) != len(box2[:4]):
        #return 0.0
    if match_class and (box1[-1]!=box2[-1]):
        #print("happened")
        return 0.0
    #print(box2[4:])
    #input(box1[4:])
    if x1y1x2y2:
        mx = min(box1[0], box2[0])
        Mx = max(box1[2], box2[2])
        my = min(box1[1], box2[1])
        My = max(box1[3], box2[3])
        w1 = box1[2] - box1[0]
        h1 = box1[3] - box1[1]
        w2 = box2[2] - box2[0]
        h2 = box2[3] - box2[1]
    else:
        mx = min(box1[0]-box1[2]/2.0, box2[0]-box2[2]/2.0)
        Mx = max(box1[0]+box1[2]/2.0, box2[0]+box2[2]/2.0)
        my = min(box1[1]-box1[3]/2.0, box2[1]-box2[3]/2.0)
        My = max(box1[1]+box1[3]/2.0, box2[1]+box2[3]/2.0)
        w1 = box1[2]
        h1 = box1[3]
        w2 = box2[2]
        h2 = box2[3]
    uw = Mx - mx
    uh = My - my
    cw = w1 + w2 - uw
    ch = h1 + h2 - uh
    carea = 0
    if cw <= 0 or ch <= 0:
        return 0.0

    area1 = w1 * h1
    area2 = w2 * h2
    carea = cw * ch
    uarea = area1 + area2 - carea
    if objsk==1:
        uarea=area1
    elif objsk==2:
        uarea=area2
    if int_only:
        return carea
    return carea/uarea

def bbox_ious(boxes1, boxes2, x1y1x2y2=True, verbose=False):
    if verbose:
        print(boxes1)
        print(boxes2)
    if x1y1x2y2:
        mx = torch.min(boxes1[0], boxes2[0])
        Mx = torch.max(boxes1[2], boxes2[2])
        my = torch.min(boxes1[1], boxes2[1])
        My = torch.max(boxes1[3], boxes2[3])
        w1 = boxes1[2] - boxes1[0]
        h1 = boxes1[3] - boxes1[1]
        w2 = boxes2[2] - boxes2[0]
        h2 = boxes2[3] - boxes2[1]
    else:
        mx = torch.min(boxes1[0]-boxes1[2]/2.0, boxes2[0]-boxes2[2]/2.0)
        Mx = torch.max(boxes1[0]+boxes1[2]/2.0, boxes2[0]+boxes2[2]/2.0)
        my = torch.min(boxes1[1]-boxes1[3]/2.0, boxes2[1]-boxes2[3]/2.0)
        My = torch.max(boxes1[1]+boxes1[3]/2.0, boxes2[1]+boxes2[3]/2.0)
        w1 = boxes1[2]
        h1 = boxes1[3]
        w2 = boxes2[2]
        h2 = boxes2[3]
    uw = Mx - mx
    uh = My - my
    cw = w1 + w2 - uw
    ch = h1 + h2 - uh
    if verbose:
        print(uw, uh, cw, ch)
    mask = ((cw <= 0) + (ch <= 0) > 0)
    area1 = w1 * h1
    area2 = w2 * h2
    carea = cw * ch
    carea[mask] = 0
    uarea = area1 + area2 - carea
    return carea/uarea

def nms(boxes, nms_thresh,xyxy=False,match_class=False):
    if len(boxes) == 0:
        return boxes

    det_confs = torch.zeros(len(boxes))
    for i in range(len(boxes)):
        #to sort in asc order
        det_confs[i] = 1-boxes[i][4]

    _,sortIds = torch.sort(det_confs)
    out_boxes = []
    for i in range(len(boxes)):
        box_i = boxes[sortIds[i]]
        if box_i[4] > 0:
            out_boxes.append(box_i)
            for j in range(i+1, len(boxes)):
                box_j = boxes[sortIds[j]]
                if bbox_iou(box_i, box_j, x1y1x2y2=xyxy, match_class=match_class) > nms_thresh:
                    #print(box_i, box_j, bbox_iou(box_i, box_j, x1y1x2y2=False))
                    box_j[4] = 0
    return out_boxes

def convert2cpu(gpu_matrix):
    return torch.FloatTensor(gpu_matrix.size()).copy_(gpu_matrix)

def convert2cpu_long(gpu_matrix):
    return torch.LongTensor(gpu_matrix.size()).copy_(gpu_matrix)

def get_region_boxes(output, conf_thresh, num_classes, anchors, num_anchors, only_objectness=1, validation=False, xyxy=False):
    #anchor_step = len(anchors)/num_anchors
    #print(output)
    #input('huh?')
    anchor_step = len(anchors)//num_anchors
    if output.dim() == 3:
        output = output.unsqueeze(0)
    batch = output.size(0)
    assert(output.size(1) == (5+num_classes)*num_anchors)
    h = output.size(2)
    w = output.size(3)

    t0 = time.time()
    all_boxes = []
    #print(output.size())
    output = output.view(batch*num_anchors, 5+num_classes, h*w)
    #print(output.size())
    output = output.transpose(0,1).contiguous()
    #print(output.size())
    output = output.view(5+num_classes, batch*num_anchors*h*w)
    #print(output.size())
    grid_x = torch.linspace(0, w-1, w).repeat(h,1).repeat(batch*num_anchors, 1, 1).view(batch*num_anchors*h*w).cuda()
    grid_y = torch.linspace(0, h-1, h).repeat(w,1).t().repeat(batch*num_anchors, 1, 1).view(batch*num_anchors*h*w).cuda()
    xs = torch.sigmoid(output[0]) + grid_x
    ys = torch.sigmoid(output[1]) + grid_y

    anchor_w = torch.Tensor(anchors).view(num_anchors, anchor_step).index_select(1, torch.LongTensor([0]))
    anchor_h = torch.Tensor(anchors).view(num_anchors, anchor_step).index_select(1, torch.LongTensor([1]))
    anchor_w = anchor_w.repeat(batch, 1).repeat(1, 1, h*w).view(batch*num_anchors*h*w).cuda()
    anchor_h = anchor_h.repeat(batch, 1).repeat(1, 1, h*w).view(batch*num_anchors*h*w).cuda()
    ws = torch.exp(output[2]) * anchor_w
    hs = torch.exp(output[3]) * anchor_h

    det_confs = torch.sigmoid(output[4])

    cls_confs = torch.nn.Softmax()(Variable(output[5:5+num_classes].transpose(0,1))).data
    #print(cls_confs.size())
    cls_max_confs, cls_max_ids = torch.max(cls_confs, 1)
    cls_max_confs = cls_max_confs.view(-1)
    cls_max_ids = cls_max_ids.view(-1)
    t1 = time.time()

    sz_hw = h*w
    sz_hwa = sz_hw*num_anchors
    det_confs = convert2cpu(det_confs)
    cls_max_confs = convert2cpu(cls_max_confs)
    cls_max_ids = convert2cpu_long(cls_max_ids)
    xs = convert2cpu(xs)
    ys = convert2cpu(ys)
    ws = convert2cpu(ws)
    hs = convert2cpu(hs)
    if validation:
        cls_confs = convert2cpu(cls_confs.view(-1, num_classes))
    t2 = time.time()
    for b in range(batch):
        boxes = []
        for cy in range(h):
            for cx in range(w):
                for i in range(num_anchors):
                    ind = b*sz_hwa + i*sz_hw + cy*w + cx
                    det_conf =  det_confs[ind]
                    if only_objectness:
                        conf = det_confs[ind]
                    else:
                        conf = det_confs[ind] * cls_max_confs[ind]

                    if conf > conf_thresh:
                        bcx = xs[ind]
                        bcy = ys[ind]
                        bw = ws[ind]
                        bh = hs[ind]
                        cls_max_conf = cls_max_confs[ind]
                        cls_max_id = cls_max_ids[ind]
                        box = [bcx/w, bcy/h, bw/w, bh/h, det_conf, cls_max_conf, cls_max_id] if not xyxy else [bcx/w - bw/(2*w), bcy/h - bh/(2*h), bcx/w + bw/(2*w), bcy/h + bh/(2*h), det_conf,  cls_max_id]
                        if (not only_objectness) and validation:
                            for c in range(num_classes):
                                tmp_conf = cls_confs[ind][c]
                                if c != cls_max_id and det_confs[ind]*tmp_conf > conf_thresh:
                                    box.append(tmp_conf)
                                    box.append(c)
                        boxes.append(box)
        all_boxes.append(boxes)
    t3 = time.time()
    if False:
        print('---------------------------------')
        print('matrix computation : %f' % (t1-t0))
        print('        gpu to cpu : %f' % (t2-t1))
        print('      boxes filter : %f' % (t3-t2))
        print('---------------------------------')
    return all_boxes

def plot_boxes_cv2(img, boxes, savename=None, class_names=None, color=None):
    import cv2
    colors = torch.FloatTensor([[1,0,1],[0,0,1],[0,1,1],[0,1,0],[1,1,0],[1,0,0]]);
    def get_color(c, x, max_val):
        ratio = float(x)/max_val * 5
        i = int(math.floor(ratio))
        j = int(math.ceil(ratio))
        ratio = ratio - i
        r = (1-ratio) * colors[i][c] + ratio*colors[j][c]
        return int(r*255)

    width = img.shape[1]
    height = img.shape[0]
    for i in range(len(boxes)):
        box = boxes[i]
        x1 = int(round((box[0] - box[2]/2.0) * width))
        y1 = int(round((box[1] - box[3]/2.0) * height))
        x2 = int(round((box[0] + box[2]/2.0) * width))
        y2 = int(round((box[1] + box[3]/2.0) * height))

        if color:
            rgb = color
        else:
            rgb = (255, 0, 0)
        if len(box) >= 7 and class_names:
            cls_conf = box[5]
            cls_id = box[6]
            print('%s: %f' % (class_names[cls_id], cls_conf))
            classes = len(class_names)
            offset = cls_id * 123457 % classes
            red   = get_color(2, offset, classes)
            green = get_color(1, offset, classes)
            blue  = get_color(0, offset, classes)
            if color is None:
                rgb = (red, green, blue)
            img = cv2.putText(img, class_names[cls_id], (x1,y1), cv2.FONT_HERSHEY_SIMPLEX, 1.2, rgb, 1)
        img = cv2.rectangle(img, (x1,y1), (x2,y2), rgb, 1)
    if savename:
        print("save plot results to %s" % savename)
        cv2.imwrite(savename, img)
    return img

def plot_boxes(img, boxes, savename=None, class_names=None, doconv=True,fontsize=35):
    colors = torch.FloatTensor([[1,0,1],[0,0,1],[0,1,1],[0,1,0],[1,1,0],[1,0,0]]);
    def get_color(c, x, max_val):
        ratio = float(x)/max_val * 5
        i = int(math.floor(ratio))
        j = int(math.ceil(ratio))
        ratio = ratio - i
        r = (1-ratio) * colors[i][c] + ratio*colors[j][c]
        return int(r*255)
    #for box in boxes:
    #    print([box[i] for i in range(4)])
    #input()
    width = img.width
    height = img.height
    draw = ImageDraw.Draw(img)

    for i in range(len(boxes)):
        box = boxes[i]
        if doconv:
            x1 = (box[0] - box[2]/2.0) * width
            y1 = (box[1] - box[3]/2.0) * height
            x2 = (box[0] + box[2]/2.0) * width
            y2 = (box[1] + box[3]/2.0) * height
        else:
            x1,y1,x2,y2=width*box[0], height*box[1], width*box[2], height*box[3]
        rgb = (255, 0, 0)
        if len(box) >= 7 and class_names:
            cls_conf = box[5]
            cls_id = int(box[6])
            print('[%i]%s: %f' % (cls_id, class_names[cls_id], cls_conf))
            classes = len(class_names)
            offset = cls_id * 123457 % classes
            red   = get_color(2, offset, classes)
            green = get_color(1, offset, classes)
            blue  = get_color(0, offset, classes)
            rgb = (red, green, blue)
            cords=(x1,y1)#((x1+x2)/2, (y1+y2)/2)
            anch='lb'
            namer=class_names[cls_id]
            #print(namer)
            #input(namer in ['dog', 'car'])
            if True:#namer in ['dog', 'car']:
                textcol=(0,0,0)
            else:
                textcol=(255,255,255)
            tangs=draw.textbbox(cords, namer, anchor=anch)
            tangs=[tangs[0]-2, tangs[1]-2, tangs[2]+2, tangs[3]+2]
            draw.rectangle(tangs, fill=rgb, outline = (0,0,0))
            draw.text(cords, namer, fill=textcol, font_size=fontsize, anchor=anch)
        draw.rectangle([x1, y1, x2, y2], outline = rgb)

    if savename:
        #input(savename)
        print("save plot results to %s" % savename)
        #img=img.resize((1024,1024))
        img.save(savename, quality=95)
    return img

def read_truths(lab_path):
    if not os.path.exists(lab_path):
        return np.array([])
    if os.path.getsize(lab_path):
        truths = np.loadtxt(lab_path)
        truths = truths.reshape(truths.size//5, 5) # to avoid single truth problem
        return truths
    else:
        return np.array([])

def read_truths_args(lab_path, min_box_scale):
    truths = read_truths(lab_path)
    new_truths = []
       # remove truths of which the width is smaller then the min_box_scale
    for i in range(truths.shape[0]):
        if truths[i][3] < min_box_scale:
            continue
        new_truths.append([truths[i][0], truths[i][1], truths[i][2], truths[i][3], truths[i][4]])
    return np.array(new_truths)

def load_class_names(namesfile):
    class_names = []
    with open(namesfile, 'r') as fp:
        lines = fp.readlines()
    for line in lines:
        line = line.rstrip()
        class_names.append(line)
    return class_names

def image2torch(img):
    width = img.width
    height = img.height
    img = torch.ByteTensor(torch.ByteStorage.from_buffer(img.tobytes()))
    img = img.view(height, width, 3).transpose(0,1).transpose(0,2).contiguous()
    img = img.view(1, 3, height, width)
    img = img.float().div(255.0)
    return img

def do_detect(model, img, conf_thresh, nms_thresh, use_cuda=1, p=None, direct_cuda_img=False, occ='fm', mode='themis', fns=False, v3=False):
    model.eval()
    t0 = time.time()
    if not direct_cuda_img:
        if isinstance(img, Image.Image):
            width = img.width
            height = img.height
            img = torch.ByteTensor(torch.ByteStorage.from_buffer(img.tobytes()))
            img = img.view(height, width, 3).transpose(0,1).transpose(0,2).contiguous()
            img = img.view(1, 3, height, width)
            img = img.float().div(255.0)
        elif type(img) == np.ndarray: # cv2 image
            img = torch.from_numpy(img.transpose(2,0,1)).float().div(255.0).unsqueeze(0)
        else:
            print("unknown image type")
            exit(-1)

    t1 = time.time()

    if use_cuda and not direct_cuda_img:
        img = img.cuda()
    img = torch.autograd.Variable(img)
    t2 = time.time()

    #SpaNN, Themis, etc.
    if not v3:
        #"""
        output, fm = model.forward(img, p=p, occ=occ, mode=mode, fns=fns) #Simen: dit doet een forward, vervangen voor duidelijkheid
        t3 = time.time()
        #print(output.shape)
        #boxes = get_region_boxes(output, conf_thresh, model.num_classes, model.anchors, model.num_anchors)[0]
        boxes = get_region_boxes(output, conf_thresh, 80, model.anchors, model.num_anchors)[0]

        #for j in range(len(boxes)):
            #print(boxes[j])
        t4 = time.time()
        #print(boxes)
        #input("benign as hell")
        boxes = nms(boxes, nms_thresh)
        t5 = time.time()
        #"""
    #FNS:
    else:
        output, fm = model.forward(img), None
        output=non_max_suppression(output, conf_thresh, nms_thresh)[0]
        if output!=None and len(output):
            boxes=[torch.cat((output[i,:5],output[i,-2:])).detach() for i in range(output.size(0))]
        else:
            boxes=[]

    if False:
        print('-----------------------------------')
        print(' image to tensor : %f' % (t1 - t0))
        print('  tensor to cuda : %f' % (t2 - t1))
        print('         predict : %f' % (t3 - t2))
        print('get_region_boxes : %f' % (t4 - t3))
        print('             nms : %f' % (t5 - t4))
        print('           total : %f' % (t5 - t0))
        print('-----------------------------------')

    return boxes, fm

def read_data_cfg(datacfg):
    options = dict()
    options['gpus'] = '0,1,2,3'
    options['num_workers'] = '10'
    with open(datacfg, 'r') as fp:
        lines = fp.readlines()

    for line in lines:
        line = line.strip()
        if line == '':
            continue
        key,value = line.split('=')
        key = key.strip()
        value = value.strip()
        options[key] = value
    return options

def scale_bboxes(bboxes, width, height):
    dets = copy.deepcopy(bboxes)
    for i in range(len(dets)):
        dets[i][0] = dets[i][0] * width
        dets[i][1] = dets[i][1] * height
        dets[i][2] = dets[i][2] * width
        dets[i][3] = dets[i][3] * height
    return dets

def file_lines(thefilepath):
    count = 0
    thefile = open(thefilepath, 'rb')
    while True:
        buffer = thefile.read(8192*1024)
        if not buffer:
            break
        count += buffer.count('\n')
    thefile.close( )
    return count

def get_image_size(fname):
    '''Determine the image type of fhandle and return its size.
    from draco'''
    with open(fname, 'rb') as fhandle:
        head = fhandle.read(24)
        if len(head) != 24:
            return
        if imghdr.what(fname) == 'png':
            check = struct.unpack('>i', head[4:8])[0]
            if check != 0x0d0a1a0a:
                return
            width, height = struct.unpack('>ii', head[16:24])
        elif imghdr.what(fname) == 'gif':
            width, height = struct.unpack('<HH', head[6:10])
        elif imghdr.what(fname) == 'jpeg' or imghdr.what(fname) == 'jpg':
            try:
                fhandle.seek(0) # Read 0xff next
                size = 2
                ftype = 0
                while not 0xc0 <= ftype <= 0xcf:
                    fhandle.seek(size, 1)
                    byte = fhandle.read(1)
                    while ord(byte) == 0xff:
                        byte = fhandle.read(1)
                    ftype = ord(byte)
                    size = struct.unpack('>H', fhandle.read(2))[0] - 2
                # We are at a SOFn block
                fhandle.seek(1, 1)  # Skip `precision' byte.
                height, width = struct.unpack('>HH', fhandle.read(4))
            except Exception: #IGNORE:W0703
                return
        else:
            return
        return width, height

def best_iou(boxes, box, verbose=False,objsk=0, match_class=False):
    best=0.0
    for b in boxes:
        iou_box = bbox_iou(box, b, x1y1x2y2=False, objsk=objsk, match_class=match_class)
        if verbose:
            print(b)
            print(iou_box)
        if iou_box>best:
            best=iou_box
    return best

def worst_iou(boxes, box, verbose=False,objsk=0, match_class=True):
    worst=1.0
    for b in boxes:
        iou_box = bbox_iou(box, b, x1y1x2y2=False, objsk=objsk, match_class=match_class)
        if verbose:
            print(b)
            print(iou_box)
        if iou_box<worst:
            worst=iou_box
    return worst

def lisf_detection(original, occlusions, ground_truth=None, thresh=0, mode= 'od', masks=None, ret_masks=False):
    '''
    local_feature	obj. det: original detection box (list of tensors)
                    img. class: numpy.ndarray, feature tensor in the shape of [feature_size_x,feature_size_y,num_cls]
    occlusions      detection boxes after occluding feature maps
    ground truth    detection to test (single object) without patch
    threshold       threshold making the original input "wrong"
    mode            object detection (od) or image classification (ic)

    Return 			obj. det: recovered bounding boxes
                    img. class: recovered class label

    '''
    if mode=='od':
        candidates=[]
        for o in occlusions:
            b_iou=best_iou(o, ground_truth)
            if b_iou > thresh:
                candidates.append(o)
                return -1, candidates

        if len(candidates)== 1:# and candidates[0] != global_pred:# and masked_conf>tau:
            return -1, candidates
        else:
            return 0, None

    elif mode=='ic':
        local_feature=original
        global_feature = np.mean(local_feature, axis=(0,1))
        pred_list = np.argsort(global_feature, kind='stable')
        global_pred = pred_list[-1]
        o_preds = []

        for ind, o in enumerate(occlusions):
            zz=np.argsort(np.mean(o, axis=(0,1)), kind='stable')[-1]
            o_preds.append(zz)
        candidates=[]

        preds, counts = np.unique(o_preds, return_counts=True)
        for p, c in zip(preds, counts):
            if c==1:# or (p==global_pred and c==2):
                candidates.append(p)
        if len(candidates)==1:
            if ret_masks:
                p=candidates[0]
                ind=np.where(o_preds==p)[0][0]
                return candidates[0], [masks[ind]]
            return candidates[0]
        else:
            if ret_masks:
                return preds[np.argmax(counts)], masks
            return preds[np.argmax(counts)]



def lisf_detection_single(original, occlusion, ground_truth=None, thresh=0, verbose=False, objsk=False, mode='od'):
    '''
    local_feature	obj. det: original detection box (list of tensors)
                    img. class: numpy.ndarray, feature tensor in the shape of [feature_size_x,feature_size_y,num_cls]

    occlusion       obj. det: boxes after occluding the image (list of tensors)
                    img. class: occluded output feature tensor after occluding one candidate
    occlusion (when gt None)     detection to test (single object), detected in occluded image
    ground truth    detection to test (single object) without patch
    threshold       threshold making the original input "wrong"
    mode            object detection (od) or image classification (ic)
    Return 			obj. det.: None or -1 for attack alert
                    img. class: class label or -1 for attack alert
    '''
    if mode=='od':
        if ground_truth is not None:
            b_iou_og=best_iou(original, ground_truth)
            b_iou=best_iou(occlusion, ground_truth)
            if b_iou >= thresh and b_iou_og < thresh:
                return -1
        else:
            if verbose:
                print(original)
                input(occlusion)
            b_iou=best_iou(original, occlusion, verbose=verbose, objsk=objsk)
            #did something appear in the image?
            if b_iou <= thresh:
                return -1
    elif mode=='ic':
        local_feature=original
        global_feature = np.mean(local_feature, axis=(0,1))
        pred_list = np.argsort(global_feature, kind='stable')
        global_pred = pred_list[-1]
        o_pred=np.argsort(np.mean(occlusion, axis=(0,1)), kind='stable')[-1]#[-1]

        if o_pred != global_pred:
            return -1
        else:
            return global_pred

def obj_seeker_score(original, occlusion):
    '''
    original	original detection box (list of tensors)
    occlusion       boxes after occluding the image (list of tensors)
    '''
    b_iou=best_iou(original, occlusion, objsk=True)
    return b_iou

def logging(message):
    print('%s %s' % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()), message))

def naive_clustering(data, metric=None):
    #overlaps = copy.deepcopy(clusters)
    convergence=False
    #print("prelims")
    #print(data)
    #input("befoah")
    while(not convergence):
        #print(clusters)
        convergence=True
        for (x1,y1,w1,h1) in data:
            merge=False
            for (x2,y2,w2,h2) in data:
               #print("clustahs: {} and {}".format(c,k))
               if (x1,y1,w1,h1)==(x2,y2,w2,h2):
                   #print("outta here")
                   continue
               elif overlap((x1,y1), (x2,y2), h1, w1, h2, w2) > min(h1*w1,h2*w2)*0.3:#(h1*w1+h2*w2)*0.3:
                   #print("joiner")
                   merge=True
                   convergence=False
                   #gift=(min(x1,x2), min(y1,y2), max(x1+w1, x2+w2)-min(x1,x2), max(y1+h1, y2+h2)-min(y1,y2))
                   gift=(int(0.5*(x1+x2)), int(0.5*(y1+y2)), w1, h1)
                   data.remove((x1,y1,w1,h1))
                   data.remove((x2,y2,w2,h2))
                   data.append(gift)
                   #
                   break
            if merge:
                break
    return data

def overlap(tup1, tup2 , wh1, ww1, wh2, ww2):
    x1, y1 = tup1
    x2, y2 = tup2
    h=min(y1+wh1, y2+wh2) - max(y1,y2)
    w=min(x1+ww1,x2+ww2) - max(x1,x2)
    return  (h>0)*(w>0)*h*w


def clustering_data_preprocessing(train_xx_np, model='2dcnn', skip=False, type='nclusters'):
    """
    train_xx_np: batch X sequence_length X channels (curves) array to be centered
    """
    if not skip:
        if type=='all':
            maxis=np.argmax(train_xx_np, axis=1)
            inds1=np.where(maxis<train_xx_np.shape[1]/2)
            inds2=np.where(maxis>=train_xx_np.shape[1]/2)
        elif type=='nclusters':
            if model=='mlp':
                maxis=np.argmax(train_xx_np, axis=1)
            else:
                maxis=np.argmax(train_xx_np[:,:,0], axis=1)
            inds1=np.where(maxis<train_xx_np.shape[1]/2)
            inds2=np.where(maxis>=train_xx_np.shape[1]/2)
        elif type=='imp_neu':
            if model in ['mlp', '1dcnn']:
                maxis=np.argmin((train_xx_np - np.max(train_xx_np, axis=1)*0.5)**2, axis=1)
            else:
                maxis=np.argmin((train_xx_np[:,:,3] -np.expand_dims(np.max(train_xx_np[:,:,3], axis=1)*0.5, axis=1))**2, axis=1)
            inds1=np.where(maxis<train_xx_np.shape[1]/2)
            inds2=np.where(maxis>=train_xx_np.shape[1]/2)
        beginings1=(train_xx_np.shape[1]/2 - maxis).astype('int')
        endings1 = (train_xx_np.shape[1] - beginings1).astype('int')
        beginings2= (maxis - train_xx_np.shape[1]/2).astype('int')
        endings2 = (train_xx_np.shape[1] - beginings2).astype('int')
        if type=='all':#args.model=='2dcnn':
            if len(inds1[0]) and len(inds1[1]):
                for k,f in zip(inds1[0], inds1[1]):
                    train_xx_np[k,beginings1[k,f]:,f] = train_xx_np[k,:endings1[k,f], f]
                    train_xx_np[k,:beginings1[k,f], f] = train_xx_np[k,beginings1[k,f], f]
            if len(inds2[0]) and len(inds2[1]):
                for k,f in zip(inds2[0], inds2[1]):
                    train_xx_np[k,:endings2[k,f], f] = train_xx_np[k,beginings2[k,f]:, f]
                    train_xx_np[k,endings2[k,f]-1:, f] = train_xx_np[k,endings2[k,f]-1,f]
        else:
            if len(inds1[0]):
                for k in inds1[0]:
                    train_xx_np[k][beginings1[k]:] = train_xx_np[k][:endings1[k]]
                    train_xx_np[k][:beginings1[k]] = train_xx_np[k][beginings1[k]]
            if len(inds2[0]):
                for k in inds2[0]:
                    train_xx_np[k][:endings2[k]] = train_xx_np[k][beginings2[k]:]
                    train_xx_np[k][endings2[k]-1:] = train_xx_np[k][endings2[k]-1]
        #return train_xx_np.reshape(-1,train_xx_np.shape[-1],train_xx_np.shape[-2])
    if model=='mlp' or model=='1dcnn':
        return train_xx_np
    else:
        return train_xx_np.transpose(0,2,1)
