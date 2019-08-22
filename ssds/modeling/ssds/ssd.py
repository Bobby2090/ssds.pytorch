import torch
import torch.nn as nn
import torch.nn.functional as F

from ssds.modeling.layers.layers_parser import parse_feature_layer
# from ssds.modeling.layers.rfb_layers   import BasicRFB, BasicRFB_lite


class SSD(nn.Module):
    """Single Shot Multibox Architecture
    See: https://arxiv.org/pdf/1512.02325.pdf for more details.

    Args:
        phase: (string) Can be "eval" or "train" or "feature"
        base: base layers for input
        extras: extra layers that feed to multibox loc and conf layers
        head: "multibox head" consists of loc and conf conv layers
        feature_layer: the feature layers for head to loc and conf
        num_classes: num of classes 
    """

    def __init__(self, base, extras, head, feature_layer, num_classes):
        super(SSD, self).__init__()
        self.num_classes = num_classes

        # SSD network
        self.base = nn.ModuleList(base)
        self.extras = nn.ModuleList(extras)

        self.loc = nn.ModuleList(head[0])
        self.conf = nn.ModuleList(head[1])
        self.softmax = nn.Softmax(dim=-1)

        self.feature_layer = feature_layer[0]

    def forward(self, x, phase='eval'):
        """Applies network layers and ops on input image(s) x.

        Args:
            x: input image or batch of images. Shape: [batch,3,300,300].

        Return:
            Depending on phase:
            test:
                Variable(tensor) of output class label predictions,
                confidence score, and corresponding location predictions for
                each object detected. Shape: [batch,topk,7]

            train:
                list of concat outputs from:
                    1: confidence layers, Shape: [batch*num_priors,num_classes]
                    2: localization layers, Shape: [batch,num_priors*4]

            feature:
                the features maps of the feature extractor
        """
        sources, loc, conf = [list() for _ in range(3)]

        # apply bases layers and cache source layer outputs
        for k in range(len(self.base)):
            x = self.base[k](x)
            if k in self.feature_layer:
                sources.append(x)

        # apply extra layers and cache source layer outputs
        for k, v in enumerate(self.extras):
            x = v(x)
            sources.append(x)

        if phase == 'feature':
            return sources

        # apply multibox head to source layers
        for (x, l, c) in zip(sources, self.loc, self.conf):
            loc.append(l(x).view(x.size(0), 4, -1))
            conf.append(c(x).view(x.size(0), self.num_classes, -1))
        loc = torch.cat(loc, 2).contiguous()
        conf = torch.cat(conf, 2).contiguous() 
        
        return loc, conf


def add_extras(base, feature_layer, mbox, num_classes):
    extra_layers = []
    loc_layers = []
    conf_layers = []
    in_channels = None
    for layer, depth, box in zip(feature_layer[0], feature_layer[1], mbox):
        extra_layers += parse_feature_layer(layer, in_channels, depth)
        in_channels = depth
        
        loc_layers += [nn.Conv2d(in_channels, box * 4, kernel_size=3, padding=1)]
        conf_layers += [nn.Conv2d(in_channels, box * num_classes, kernel_size=3, padding=1)]
    return base, extra_layers, (loc_layers, conf_layers)
    
   
def build_ssd(base, feature_layer, mbox, num_classes):
    """Single Shot Multibox Architecture
    See: https://arxiv.org/pdf/1512.02325.pdf and
    https://arxiv.org/pdf/1801.04381.pdf for more details.
    """
    base_, extras_, head_ = add_extras(base(), feature_layer, mbox, num_classes)
    return SSD(base_, extras_, head_, feature_layer, num_classes)