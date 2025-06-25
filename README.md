## KEX Project: Patch Attacks
# Adversarial Patch Attacks & Defenses – Object Detection & Classification

This project provides tools and scripts for applying, training, and evaluating adversarial patch attacks on object detection and image classification models. It includes preconfigured scripts for YOLOv2 and ResNet50-based models, support for public datasets (INRIA, Pascal VOC, ImageNet, CIFAR-10), and defenses using the NutNet architecture.



## Directory Overview

- **`cfg/`** – Config files for object detection models (YOLOv2 by default)  
- **`checkpoints/`** – Model weights for image classification (e.g., ResNet50 trained on CIFAR-10)  
- **`data/`** – Sample data from object detection (INRIA, Pascal VOC) and classification (ImageNet, CIFAR-10) datasets  
- **`nets/`** – Torch models used for image classification (e.g., ResNet50)  
- **`patches/`** – Pretrained patch images ready for application  
- **`utils/`** – Helper functions for object detection (`utils.py`)  
- **`weights/`** – Place YOLOv2 weights (`yolo.weights`) here (not included due to file size)

## Key Files

- `cfg.py`, `darknet.py`, `region_loss.py` – Required for running YOLOv2 with PyTorch  
- `helper.py` – Object detection helper utilities  
- `patch_folder_creator.py`, `patch_folder_creator_ic.py` – Apply patches on detection/classification datasets  
- `load_data.py`, `median_pool.py` – Used for patch training and application  
- `PatchAttacker.py` – Runs non-universal patch attacks (classification only)


### Required Downloads

- **CIFAR-10 attacks**: Download `resnet50_192_cifar.pth` from PatchGuard and place in `checkpoints/` *(already done)*  
- **YOLOv2 attacks**: Download `yolo.weights` following instructions from adversarial_yolo2 and place in `weights/` *(required)*

## Apply Pretrained Patches

Apply patches to clean images using the provided scripts.

### Single Patch (Object Detection – INRIA)
```
python patch_folder_creator.py --imgdir data/inria/clean/ --n_patches 1 --patchfile patches/newpatch.PNG --p_name test/
```

### Double Patch (Object Detection)
```
python patch_folder_creator.py --imgdir data/inria/clean/ --n_patches 2 --patchfile patches/newpatch.PNG --p_name test/
```

### Multiple Targets per Image
```
python patch_folder_creator.py --imgdir data/inria/clean/ --n_patches 1 --patchfile patches/newpatch.PNG --p_name test/ --max_lab 3
```

### Classification Patch (e.g. ImageNet – 32x32)
```
python patch_folder_creator_ic.py --imgdir data/imagenet/clean/ --dataset imagenet --n_patches 1 --patchfile patches/imgnet_patch.PNG --p_name test/ --patch_size 32
```

## Train Patches

Train a universal adversarial patch using labeled data.

### Train on INRIA Clean Images
```
python train_patch.py --patience 100 --imgdir data/inria/clean --labdir data/inria/yolo-labels/ --savedir testing/
```

The resulting patch will be saved as `testing/universal_patch.png`.

## Defense & Evaluation with NutNet

Evaluate patch effectiveness and visualize detection results.

### Clean Image Baseline (Undefended)
```
python nutnet.py --imgdir data/inria/clean --patch_imgdir data/inria/1p/ --bypass --visualize --clean --savedir undefended_clean/
```

### Undefended Model – Single Patch Attack
```
python nutnet.py --imgdir data/inria/clean --patch_imgdir data/inria/1p/ --bypass --visualize --savedir undefended_1p/
```


## External Sources & Dependencies

This repository builds upon:
- https://github.com/Zhang-Jack/adversarial_yolo2  
- https://github.com/inspire-group/PatchGuard/tree/master

### NutNet Defense – Single Patch Attack
```
python nutnet.py --imgdir data/inria/clean --patch_imgdir data/inria/1p/ --visualize --savedir nutnet_1p/
```

