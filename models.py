import numpy as np
import torch
import torch.nn as nn
# import torch.utils.data
# import pickle

GPU_ID = 0
CUDA = True

class Model(object):
    def __init__(self, mult_chan, depth):
        self.name = 'chek model'
        self.net = Net(mult_chan=mult_chan, depth=depth)
        # self.net = Net_bk(mult_chan)
        print(self.net)
        if CUDA:
            self.net.cuda()

        lr = 0.0001
        momentum = 0.5
        # self.optimizer = torch.optim.SGD(self.net.parameters(), lr=lr, momentum=momentum)
        self.optimizer = torch.optim.Adam(self.net.parameters(), lr=lr, betas=(0.5, 0.999))
        self.criterion = torch.nn.MSELoss()
        # self.criterion = torch.nn.BCELoss()

        self.count_iter = 0

    def save(self, fname):
        raise NotImplementedError
        print('saving model to:', fname)
        package = (self.net, self.mean_features, self.std_features)
        fo = open(fname, 'wb')
        pickle.dump(package, fo)
        fo.close()

    def load(self, fname):
        raise NotImplementedError
        print('loading model:', fname)
        classifier_tup = pickle.load(open(fname, 'rb'))
        self.net = classifier_tup[0]
        self.mean_features = classifier_tup[1]
        self.std_features = classifier_tup[2]

    def _split_data(self, x, y, portion_test=0.1):
        idx = int((1 - portion_test)*x.shape[0])
        x_train = x[0:idx]
        x_val = x[idx:]
        y_train = y[0:idx]
        y_val = y[idx:]
        return x_train, y_train, x_val, y_val

    def do_train_iter(self, signal, target):
        self.net.train()
        if CUDA:
            signal_t, target_t = torch.Tensor(signal).cuda(), torch.Tensor(target).cuda()
        else:
            signal_t, target_t = torch.Tensor(signal), torch.Tensor(target)
        signal_v, target_v = torch.autograd.Variable(signal_t), torch.autograd.Variable(target_t)
        self.optimizer.zero_grad()
        output = self.net(signal_v)
        loss = self.criterion(output, target_v)
        
        loss.backward()
        self.optimizer.step()
        print("iter: {:3d} | loss: {:4f}".format(self.count_iter, loss.data[0]))
        self.count_iter += 1
    
    def train_legacy(self, x, y, validate=False):
        """
        Parameters:
        validate -- boolean. Set to True to split training data into additional validation set. After each epoch, the validation
          data will be applied to the current model.
        """
        if validate:
            features_train_pre, labels_train, features_val_pre, labels_val = self._split_data(x, y)
        else:
            features_train_pre, labels_train = x, y
            
        lr = 0.001
        n_epochs = 100

        n_features = features_train_pre.shape[1]

        # feature mean substraction and normalization
        self.mean_features = np.mean(features_train_pre, axis=0)
        self.std_features = np.std(features_train_pre, axis=0)
        self.std_features[self.std_features == 0] = 1  # to avoid division by zero
        features_train = (features_train_pre - self.mean_features)/self.std_features

        dataset = torch.utils.data.TensorDataset(torch.Tensor(features_train), torch.Tensor(labels_train))
        trainloader = torch.utils.data.DataLoader(dataset, batch_size=64, shuffle=True)

        self.net = Net2(n_features, dr=0.9).cuda(GPU_ID)
        print(self.net)
        optimizer = torch.optim.Adam(self.net.parameters(), lr=lr, betas=(0.5, 0.999))
        criterion = torch.nn.BCELoss().cuda(GPU_ID)
        losses_train = np.zeros(n_epochs)

        if validate:
            features_val = (features_val_pre - self.mean_features)/self.std_features
            losses_val = np.zeros(n_epochs)

        print('{:s}: training with {:d} examples'.format(self.name, labels_train.shape[0]))
        for epoch in range(n_epochs):
            sum_train_loss = 0
            for data in trainloader:
                inputs, labels = torch.autograd.Variable(data[0]).cuda(GPU_ID), torch.autograd.Variable(data[1].float()).cuda(GPU_ID)
                optimizer.zero_grad()
                output = self.net(inputs)
                loss = criterion(output, labels)
                loss.backward()
                optimizer.step()
                sum_train_loss += loss.data[0]
            losses_train[epoch] = sum_train_loss/len(trainloader)
            optimizer.param_groups[0]['lr'] = lr*(0.999**epoch)

            if validate:
                # Validate current model
                features_val_v = torch.autograd.Variable(torch.FloatTensor(features_val)).cuda(GPU_ID)
                labels_val_v = torch.autograd.Variable(torch.FloatTensor(labels_val)).cuda(GPU_ID)
                self.net.eval()
                labels_pred_val = self.net(features_val_v)
                loss = criterion(labels_pred_val, labels_val_v)        
                self.net.train()
                losses_val[epoch] = loss.data[0]
                print('epoch: {:3d} | training loss: {:.4f} | test loss: {:.4f}'.format(epoch, losses_train[epoch], losses_val[epoch]))
            else:
                print('epoch: {:3d} | training loss: {:.4f}'.format(epoch, losses_train[epoch]))

    def score(self, x):
        print('{:s}: scoring {:d} examples'.format(self.name, x.shape[0]))
        features_pp = (x - self.mean_features)/self.std_features
        self.net.eval()
        features_pp_v = torch.autograd.Variable(torch.FloatTensor(features_pp)).cuda(GPU_ID)
        scores_v = self.net(features_pp_v)
        scores_np = scores_v.data.cpu().numpy()
        return scores_np

    def predict(self, signal):
        print('{:s}: predicting {:d} examples'.format(self.name, signal.shape[0]))
        self.net.eval()
        if CUDA:
            signal_t = torch.Tensor(signal).cuda()
        else:
            signal_t = torch.Tensor(signal)
        signal_v = torch.autograd.Variable(signal_t)
        pred_v = self.net(signal_v)
        pred_np = pred_v.data.cpu().numpy()
        return pred_np

class Net_bk(nn.Module):
    def __init__(self, param_1=16):
        super().__init__()
        self.sub_1 = SubNet2Conv(1, param_1)
        self.pool_1 = torch.nn.MaxPool3d(2, stride=2)
        self.sub_2 = SubNet2Conv(param_1, param_1*2)
        self.convt = torch.nn.ConvTranspose3d(param_1*2, param_1, kernel_size=2, stride=2)
        self.sub_3 = SubNet2Conv(param_1*2, param_1)
        self.conv_out = torch.nn.Conv3d(param_1,  1, kernel_size=3, padding=1)
        
    def forward(self, x):
        x1 = self.sub_1(x)
        x1d = self.pool_1(x1)
        x2 = self.sub_2(x1d)
        x2u = self.convt(x2)  # upsample
        x1_2 = torch.cat((x1, x2u), 1)  # concatenate
        x3 = self.sub_3(x1_2)
        x_out = self.conv_out(x3)
        return x_out

class Net(nn.Module):
    def __init__(self, mult_chan=16, depth=1):
        super().__init__()
        self.net_recurse = _Net_recurse(n_in_channels=1, mult_chan=mult_chan, depth=depth)
        self.conv_out = torch.nn.Conv3d(mult_chan,  1, kernel_size=3, padding=1)
        self.sig = torch.nn.Sigmoid()

    def forward(self, x):
        x_rec = self.net_recurse(x)
        x_pre_out = self.conv_out(x_rec)
        x_out = self.sig(x_pre_out)
        # return x_pre_out
        return x_out

class _Net_recurse(nn.Module):
    def __init__(self, n_in_channels, mult_chan=2, depth=0):
        """Class for recursive definition of U-network.p

        Parameters:
        in_channels - (int) number of channels for input.
        mult_chan - (int) factor to determine number of output channels
        depth - (int) if 0, this subnet will only be convolutions that double the channel count.
        """
        super().__init__()
        self.depth = depth
        n_out_channels = n_in_channels*mult_chan
        self.sub_2conv_more = SubNet2Conv(n_in_channels, n_out_channels)
        if depth > 0:
            self.sub_2conv_less = SubNet2Conv(2*n_out_channels, n_out_channels)
            self.pool = torch.nn.MaxPool3d(2, stride=2)
            self.convt = torch.nn.ConvTranspose3d(2*n_out_channels, n_out_channels, kernel_size=2, stride=2)
            self.sub_u = _Net_recurse(n_out_channels, mult_chan=2, depth=(depth - 1))
            
    def forward(self, x):
        if self.depth == 0:
            return self.sub_2conv_more(x)
        else:  # depth > 0
            x_2conv_more = self.sub_2conv_more(x)
            x_pool = self.pool(x_2conv_more)
            x_sub_u = self.sub_u(x_pool)
            x_convt = self.convt(x_sub_u)
            x_cat = torch.cat((x_2conv_more, x_convt), 1)  # concatenate
            x_2conv_less = self.sub_2conv_less(x_cat)
        return x_2conv_less

    
class SubNet2Conv(nn.Module):
    def __init__(self, n_in, n_out):
        super().__init__()
        self.conv1 = nn.Conv3d(n_in,  n_out, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm3d(n_out)
        self.relu1 = nn.ReLU()
        self.conv2 = nn.Conv3d(n_out, n_out, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm3d(n_out)
        self.relu2 = nn.ReLU()

    def forward(self, x):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu1(x)
        x = self.conv2(x)
        x = self.bn2(x)
        x = self.relu2(x)
        return x