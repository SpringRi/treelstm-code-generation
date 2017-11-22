import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.nn.init as init
from torch.autograd import Variable as Var


class ChildSumTreeLSTM(nn.Module):
    def __init__(self, in_dim, mem_dim, p_dropout=0.0):
        super().__init__()

        self.in_dim = in_dim
        self.mem_dim = mem_dim

        self.ioux = nn.Linear(self.in_dim, 3 * self.mem_dim)
        init.uniform(self.ioux.weight)

        self.iouh = nn.Linear(self.mem_dim, 3 * self.mem_dim)
        init.orthogonal(self.iouh.weight)

        self.fx = nn.Linear(self.in_dim, self.mem_dim)
        init.uniform(self.fx.weight)

        self.fh = nn.Linear(self.mem_dim, self.mem_dim)
        init.orthogonal(self.fh.weight)

        self.dropout = nn.AlphaDropout(p=p_dropout)

    def node_forward(self, inputs, child_c, child_h):
        child_h_sum = torch.sum(child_h, dim=0, keepdim=True)

        iou = self.ioux(inputs) + self.iouh(child_h_sum)
        # u is c tilda - the new value of memory cell
        i, o, u = torch.split(iou, iou.size(1) // 3, dim=1)
        i, o, u = F.sigmoid(i), F.sigmoid(o), F.tanh(u)

        f = F.sigmoid(
            self.fh(child_h) +
            self.fx(inputs).repeat(len(child_h), 1)
        )
        fc = torch.mul(f, child_c)

        c = torch.mul(i, u) + torch.sum(fc, dim=0, keepdim=True)
        h = torch.mul(o, F.tanh(c))
        return c, h #self.dropout(h)

    def forward_inner(self, tree, inputs):
        _ = [self.forward_inner(tree.children[idx], inputs) for idx in range(tree.num_children)]

        if tree.num_children == 0:
            child_c = Var(inputs[0].data.new(1, self.mem_dim).fill_(0.))
            child_h = Var(inputs[0].data.new(1, self.mem_dim).fill_(0.))
        else:
            child_c, child_h = zip(*map(lambda x: x.state, tree.children))
            child_c, child_h = torch.cat(child_c, dim=0), torch.cat(child_h, dim=0)

        tree.state = self.node_forward(inputs[tree.idx], child_c, child_h)
        return tree.state

    def forward(self, tree, inputs):
        inputs = self.dropout(inputs)
        self.forward_inner(tree, inputs)
        return tree.state[1].squeeze(), torch.stack([t.state[1] for t in tree.data()]).squeeze()