import os
import lmdb  # install lmdb by "pip install lmdb"
import cv2

import numpy as np


def checkImageIsValid(imageBin):
    if imageBin is None:
        return False
    try:
        imageBuf = np.fromstring(imageBin, dtype=np.uint8)
        img = cv2.imdecode(imageBuf, cv2.IMREAD_GRAYSCALE)
        imgH, imgW = img.shape[0], img.shape[1]
    except BaseException:
        return False
    else:
        if imgH * imgW == 0:
            return False
    return True


def writeCache(env, cache):
    with env.begin(write=True) as txn:
        for k, v in cache.items():
            txn.put(str(k).encode(), str(v).encode())


def createDataset(outputPath, imagePathList, labelList,
                  lexiconList=None, checkValid=True):
    """
    Create LMDB dataset for CRNN training.
    ARGS:
        outputPath    : LMDB output path
        imagePathList : list of image path
        labelList     : list of corresponding groundtruth texts
        lexiconList   : (optional) list of lexicon lists
        checkValid    : if true, check the validity of every image
    """
    assert (len(imagePathList) == len(labelList))
    nSamples = len(imagePathList)
    env = lmdb.open(outputPath, map_size=59511627776)
    cache = {}
    cnt = 1
    for i in range(nSamples):
        imagePath = ''.join(
            imagePathList[i]).split()[0].replace(
            '\n',
            '').replace(
            '\r\n',
            '')
        # 将目录与文件名结合形成文件绝对路径
        imagePath = r'D:\pythonproject\\temp\out\\' + imagePath
        label = ''.join(labelList[i])
        if not os.path.exists(imagePath):
            print('%s does not exist' % imagePath)
            continue

        with open(imagePath, 'rb') as f:
            imageBin = f.read()

        if checkValid:
            if not checkImageIsValid(imageBin):
                print('%s is not a valid image' % imagePath)
                continue
        imageKey = 'image-%09d' % cnt
        labelKey = 'label-%09d' % cnt
        cache[imageKey] = imageBin
        cache[labelKey] = label
        if lexiconList:
            lexiconKey = 'lexicon-%09d' % cnt
            cache[lexiconKey] = ' '.join(lexiconList[i])
        if cnt % 1000 == 0:
            writeCache(env, cache)
            cache = {}
            print('Written %d / %d' % (cnt, nSamples))
        cnt += 1
        print(cnt)
    nSamples = cnt - 1
    cache['num-samples'] = str(nSamples)
    writeCache(env, cache)
    print('Created dataset with %d samples' % nSamples)


if __name__ == '__main__':
    outputPath = "train_lmdb/"
    imgdata = open("out/labels.txt", encoding='utf-8')
    imagePathList = list(imgdata)
    print(len(imagePathList))
    labelList = []
    for line in imagePathList:
        word = line.split()[1]
        labelList.append(word)
    createDataset(outputPath, imagePathList, labelList)
