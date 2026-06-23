import torch

print(torch.cuda.get_device_name(0))

x = torch.rand(10000, 10000).cuda()
y = torch.rand(10000, 10000).cuda()

z = torch.matmul(x, y)

print(z.shape)