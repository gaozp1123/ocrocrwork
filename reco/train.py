import Config
import random
import os
import numpy as np
import torch
from torch.nn import CTCLoss
import torch.backends.cudnn as cudnn
import lib.dataset
import lib.convert
import lib.utility
from torch.autograd import Variable
import Net.net as Net
import torch.optim as optim
from torch.utils.tensorboard import SummaryWriter


def val(net, da, criterion, max_iter=100):
    print('Start val')
    net.eval()
    with torch.no_grad():
        data_loader = torch.utils.data.DataLoader(
            da, shuffle=True, batch_size=Config.batch_size, num_workers=int(Config.data_worker))
        val_iter = iter(data_loader)

        i = 0
        n_correct = 0
        loss_avg = lib.utility.averager()

        max_iter = min(max_iter, len(data_loader))
        for i in range(max_iter):
            data = val_iter.next()
            i += 1
            cpu_images, cpu_texts = data
            batch_size = cpu_images.size(0)
            lib.dataset.loadData(image, cpu_images)
            t, l = converter.encode(cpu_texts)
            lib.dataset.loadData(text, t)
            lib.dataset.loadData(length, l)

            preds = net(image)
            preds_size = torch.IntTensor([preds.size(0)] * batch_size)
            cost = criterion(preds, text, preds_size, length) / batch_size
            loss_avg.add(cost)

            _, preds = preds.max(2)
            preds = preds.transpose(1, 0).contiguous().view(-1)
            sim_preds = converter.decode(preds.data, preds_size.data, raw=False)
            list_1 = []
            for i in cpu_texts:
                list_1.append(i.decode('utf-8', 'strict'))
            for pred, target in zip(sim_preds, list_1):
                if pred == target:
                    n_correct += 1

    accuracy = n_correct / float(max_iter * Config.batch_size)
    print('Test loss: %f, accuray: %f' % (loss_avg.val(), accuracy))
    return loss_avg.val(), accuracy


def trainBatch(net, criterion, optimizer, train_iter):
    data = train_iter.next()
    cpu_images, cpu_texts = data
    batch_size = cpu_images.size(0)
    lib.dataset.loadData(image, cpu_images)
    t, l = converter.encode(cpu_texts)
    lib.dataset.loadData(text, t)
    lib.dataset.loadData(length, l)
    # print("------------------")
    # print(image.device)
    # print(text.device)
    # print(type(text))
    # print("------------------")
    preds = net(image)

    preds_size = Variable(torch.IntTensor(
        [preds.size(0)] * batch_size))  # preds.size(0)=w=22
    cost = criterion(preds, text, preds_size, length) / batch_size
    net.zero_grad()
    cost.backward()
    optimizer.step()
    return cost


if __name__ == '__main__':
    torch.multiprocessing.set_start_method('spawn')
    if not os.path.exists(Config.model_dir):
        os.mkdir(Config.model_dir)

    print("image scale: [%s,%s]\nmodel_save_path: %s\ngpu_id: %s\nbatch_size: %s" %
          (Config.img_height, Config.img_width, Config.model_dir, Config.gpu_id, Config.batch_size))

    random.seed(Config.random_seed)
    np.random.seed(Config.random_seed)
    torch.manual_seed(Config.random_seed)
    device = torch.device("cuda:0" if torch.cuda.is_available()
                          and Config.using_cuda else "cpu")
    train_dataset = lib.dataset.lmdbDataset(root=Config.train_data)
    test_dataset = lib.dataset.lmdbDataset(
        root=Config.test_data, transform=lib.dataset.resizeNormalize(
            (Config.img_width, Config.img_height)))
    assert train_dataset

    # images will be resize to 32*100
    train_loader = torch.utils.data.DataLoader(
        train_dataset,
        batch_size=Config.batch_size,
        shuffle=True,
        num_workers=int(Config.data_worker),
        collate_fn=lib.dataset.alignCollate(imgH=Config.img_height, imgW=Config.img_width))

    n_class = len(Config.alphabet) + 1  # for python3
    # n_class = len(Config.alphabet.decode('utf-8')) + 1  # for python2
    print("alphabet class num is %s" % n_class)
    # 文字标签化
    converter = lib.convert.strLabelConverter(Config.alphabet)

    criterion = CTCLoss()

    net = Net.CRNN(n_class)
    #  引用参数
    net.load_state_dict(torch.load("../weights/crnn/netCRNN_4_48000.pth"))
    # net.apply(lib.utility.weights_init)
    # print("this is pretrain model parameters:")
    # print(net.state_dict())
    image = torch.FloatTensor(
        Config.batch_size,
        3,
        Config.img_height,
        Config.img_width)
    text = torch.IntTensor(Config.batch_size * 5)
    length = torch.IntTensor(Config.batch_size)

    net.to(device)
    image = image.cuda()

    # for p in net.parameters():
    #     print(p.device)

    loss_avg = lib.utility.averager()

    optimizer = optim.RMSprop(net.parameters(), lr=Config.lr)
    writer = SummaryWriter('runs/crnn')
    temp_input = torch.zeros((64, 1, 32, 168), device=device)
    writer.add_graph(net, temp_input)
    for epoch in range(Config.epoch):
        train_iter = iter(train_loader)
        i = 0
        while i < len(train_loader):
            net.train()

            cost = trainBatch(net, criterion, optimizer, train_iter)
            loss_avg.add(cost)
            i += 1

            if i % Config.log_interval == 0:
                writer.add_scalar("training loss",
                                  loss_avg.val(),
                                  epoch * len(train_loader) + i
                                  )

            if i % Config.display_interval == 0:
                print('[%d/%d][%d/%d] Loss: %f' %
                      (epoch, Config.epoch, i, len(train_loader), loss_avg.val()))
                loss_avg.reset()

            if i % Config.test_interval == 0:
                loss, accuracy = val(net, test_dataset, criterion)
                writer.add_scalar(
                    'test/loss', loss, epoch * len(train_loader) + i)
                writer.add_scalar(
                    'test/accuracy', accuracy, epoch * len(train_loader) + i)

            # do checkpointing
            if i % Config.save_interval == 0:
                torch.save(
                    net.state_dict(), '{0}/CRNN_{1}_{2}.pth'.format(Config.model_dir, epoch, i))
