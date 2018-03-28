import json
import numpy as np
import os
import pickle
import random
import sys
import time
import torch
import torch.nn as nn
import torch.utils.data as Data
import torch.nn.functional as F

from google.colab import files
from nltk.corpus import stopwords
from torch.autograd import Variable
from tqdm import tqdm
from sklearn import metrics
from datetime import timedelta
en_stop = set(stopwords.words('english'))
use_cuda = torch.cuda.is_available()
BATCH_SIZE = 500
EPOCHS = 10

print("Lodaing Vocab")
word2idx = pickle.load(open("word2idx", "rb"))
V = len(word2idx)

max_length = 300
embed_size = 128
model_file = "hc.model"


def pad(x):
    while(len(x) % BATCH_SIZE != 0):
        x.append(x[-1])
    return x

    print("Lodaing Vocab")


word2idx = pickle.load(open("word2idx", "rb"))
V = len(word2idx)

max_length = 300
embed_size = 128
model_file = "hc.model"

print("\nReading Training Data\n")
data = []
with open("dataset/audio_train.json", "r") as f:
    for line in tqdm(f):
        data.append(json.loads(line))

print("\nExtracting x's and y's\n")
corpus = [(each["summary"] + " ") * 4 + each["reviewText"] for each in data]
y_train = [int(each["overall"] - 1) for each in data]
y_train = [0 if i == 0 or i == 1 else 2 if i == 3 or i == 4 else 1 for i in y_train]

del data
print("\nRemoving stopwords\n")
x_train = []
for each in tqdm(corpus):
    temp = each.lower().split()
    x_train.append([word2idx[i] for i in temp if i not in en_stop])
del corpus

print("\nCoverting to sets\n")
for i in tqdm(range(len(x_train))):
    x_train[i] = list(set(x_train[i]))


for i in tqdm(range(len(x_train))):
    if len(x_train[i]) < max_length:
        x_train[i] = x_train[i] + [V + 1 for j in range(max_length - len(x_train[i]))]
    else:
        x_train[i] = x_train[i][0:max_length]

x_train = pad(x_train)
y_train = pad(y_train)
x_train = torch.from_numpy(np.array(x_train))
y_train = torch.from_numpy(np.array(y_train))

if use_cuda:
    x_train = x_train.cuda()
    y_train = y_train.cuda()

print("\nReading Dev Data\n")
data = []
with open("dataset/audio_dev.json", "r") as f:
    for line in tqdm(f):
        data.append(json.loads(line))

print("\nExtracting x's and y's\n")
corpus = [(each["summary"] + " ") * 4 + each["reviewText"] for each in data]
y_dev = [int(each["overall"] - 1) for each in data]
y_dev = [0 if i == 0 or i == 1 else 2 if i == 3 or i == 4 else 1 for i in y_dev]

del data
print("\nRemoving stopwords\n")
x_dev = []
for each in tqdm(corpus):
    temp = each.lower().split()
    x_dev.append([word2idx[i] for i in temp if i not in en_stop])
del corpus

print("\nCoverting to sets\n")
for i in tqdm(range(len(x_dev))):
    x_dev[i] = list(set(x_dev[i]))

for i in tqdm(range(len(x_dev))):
    if len(x_dev[i]) < max_length:
        x_dev[i] = x_dev[i] + [V + 1 for j in range(max_length - len(x_dev[i]))]
    else:
        x_dev[i] = x_dev[i][0:max_length]

x_dev = pad(x_dev)
y_dev = pad(y_dev)
data = random.sample(list(zip(x_dev, y_dev)), 1000)
sample_x_dev, sample_y_dev = zip(*data)

x_dev = torch.from_numpy(np.array(x_dev))
y_dev = torch.from_numpy(np.array(y_dev))
sample_x_dev = torch.from_numpy(np.array(pad(sample_x_dev)))
sample_y_dev = torch.from_numpy(np.array(pad(sample_y_dev)))

if use_cuda:
    x_dev = x_dev.cuda()
    y_dev = y_dev.cuda()
    sample_x_dev = sample_x_dev.cuda()
    sample_y_dev = sample_y_dev.cuda()


class hc_LSTM(nn.Module):
    def __init__(self, embedding_dim, hidden_dim, vocab_size, label_size):
        super(hc_LSTM, self).__init__()
        self.hidden_dim = hidden_dim
        self.word_embeddings = nn.Embedding(vocab_size, embedding_dim)
        self.lstm = nn.LSTM(embedding_dim, hidden_dim, num_layers=1, batch_first=True)
        self.hidden2label = nn.Linear(hidden_dim, label_size)
        self.hidden = self.init_hidden(BATCH_SIZE)

    def init_hidden(self, batch_size):
        a = torch.zeros(1, batch_size, self.hidden_dim)
        b = torch.zeros(1, batch_size, self.hidden_dim)
        if use_cuda:
            a = a.cuda()
            b = b.cuda()

        return Variable(a), Variable(b)

    def forward(self, data):
        embeds = self.word_embeddings(data)
        lstm_out, self.hidden = self.lstm(embeds, self.hidden)
        out = self.hidden2label(lstm_out[:, -1, :])
        return out


dataset = torch.utils.data.TensorDataset(x_dev, y_dev)
dev_loader = Data.DataLoader(dataset=dataset, batch_size=BATCH_SIZE, shuffle=True)

dataset = torch.utils.data.TensorDataset(sample_x_dev, sample_y_dev)
sample_dev_loader = Data.DataLoader(dataset=dataset, batch_size=BATCH_SIZE, shuffle=True)


def evaluate(data_loader, model, loss, data_len, verbose=False):
    model.eval()  # set mode to evaluation to disable dropout
    total_loss = 0.0
    y_true, y_pred = [], []

    count = 0
    for data, label in data_loader:
        count += 1
        if verbose:
            sys.stdout.write("\r\x1b[K %d/%d" % (count, len(data_loader)))
            sys.stdout.flush()
        data, label = Variable(data, volatile=True), Variable(label, volatile=True)
        if use_cuda:
            data, label = data.cuda(), label.cuda()

        output = model(data)
        losses = loss(output, label)

        total_loss += losses.data[0]
        pred = torch.max(output.data, dim=1)[1].cpu().numpy().tolist()
        y_pred.extend(pred)
        y_true.extend(label.data)
    if verbose:
        print()
    acc = (np.array(y_true) == np.array(y_pred)).sum()
    fscore = metrics.f1_score(y_true, y_pred, average="macro")
    return acc / data_len, total_loss / data_len, fscore


def get_time_dif(start_time):
    end_time = time.time()
    time_dif = end_time - start_time
    return timedelta(seconds=int(round(time_dif)))


def test(model, test_loader):
    print("Testing...")
    start_time = time.time()

    # restore the best parameters
    model.load_state_dict(torch.load(model_file, map_location=lambda storage, loc: storage))

    y_true, y_pred = [], []
    for data, label in tqdm(test_loader):
        data, label = Variable(data, volatile=True), Variable(label, volatile=True)
        if use_cuda:
            data, label = data.cuda(), label.cuda()

        output = model(data)
        pred = torch.max(output.data, dim=1)[1].cpu().numpy().tolist()
        y_pred.extend(pred)
        y_true.extend(label.data)

    test_acc = metrics.accuracy_score(y_true, y_pred)
    test_f1 = metrics.f1_score(y_true, y_pred, average='macro')
    print("Test accuracy: {0:>7.2%}, F1-Score: {1:>7.2%}".format(test_acc, test_f1))

    print("Precision, Recall and F1-Score...")
    print(metrics.classification_report(y_true, y_pred, target_names=['0', '1', '2']))

    print('Confusion Matrix...')
    cm = metrics.confusion_matrix(y_true, y_pred)
    print(cm)

    print("Time usage:", get_time_dif(start_time))


def train():

    start_time = time.time()
    model = hc_LSTM(embed_size, 32, V + 2, 3)
    print(model)

    if os.path.exists(model_file):
        print("Loading Model")
        model.load_state_dict(torch.load(model_file, map_location=lambda storage, loc: storage))
    if use_cuda:
        model.cuda()

    # optimizer and loss function
    criterion = nn.CrossEntropyLoss(size_average=False)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    # set the mode to train
    print("Training and evaluating...")
    dataset = torch.utils.data.TensorDataset(x_train, y_train)
    train_loader = Data.DataLoader(dataset=dataset, batch_size=BATCH_SIZE, shuffle=True)

    best_fscore = 0.0
    for epoch in range(EPOCHS):
        # load the training data in batch
        model.train()
        iter = 0
        for x_batch, y_batch in tqdm(train_loader):
            inputs, targets = Variable(x_batch), Variable(y_batch)
            if use_cuda:
                inputs, targets = inputs.cuda(), targets.cuda()

            optimizer.zero_grad()
            model.hidden = model.init_hidden(BATCH_SIZE)
#             print(inputs.volatile)
            outputs = model(inputs)  # forward computation
#             print(outputs.volatile)
            loss = criterion(outputs, targets)
#             print(loss.volatile)

            # backward propagation and update parameters
            loss.backward()
            optimizer.step()
            if iter % 1000 == 0:
                test_acc, test_loss, fscore = evaluate(sample_dev_loader, model, criterion, len(sample_y_dev))
                print(test_acc, test_loss, fscore)
                model.train()

            iter += 1
        # evaluate on both training and test dataset
        # train_acc, train_loss = evaluate(train_loader, model, criterion, len(y_train))
        test_acc, test_loss, fscore = evaluate(dev_loader, model, criterion, len(y_dev), verbose=True)

        if fscore > best_fscore:
            # store the best result
            best_fscore = fscore
            improved_str = '*'
            torch.save(model.state_dict(), model_file)

        else:
            improved_str = ''

        time_dif = get_time_dif(start_time)
        msg = "Epoch {0:3}, " \
              + "Test_loss: {1:>6.2}, Test_acc {2:>6.2%}, Fscore {3:6.2%} Time: {4} {5}"
        print(msg.format(epoch + 1, test_loss, test_acc, fscore, time_dif, improved_str))
    test(model, dev_loader)