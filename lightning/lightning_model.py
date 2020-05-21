import os
from typing import NamedTuple

import pytorch_lightning as pl
import torch
from pytorch_lightning import Trainer
from test_tube import HyperOptArgumentParser
from collections import OrderedDict
import torch as t
import numpy as np
import torch.nn.functional as F
from torch.nn.utils.rnn import pad_sequence
from torch.utils.data.dataloader import DataLoader

from data_related.audio_feature_extraction import AudioFeaturesConfig
from data_related.char_stt_dataset import DataConfig, CharSTTDataset
from data_related.librispeech import LIBRI_VOCAB, build_librispeech_corpus
from model import DeepSpeech
from utils import BLANK_SYMBOL


class Params(NamedTuple):
    hidden_size: int
    hidden_layers: int
    audio_feature_dim: int
    vocab_size: int
    bidirectional: bool = True


class LitSTTModel(pl.LightningModule):
    def __init__(self, hparams: Params):
        super().__init__()
        self.hparams = hparams
        self.lr = 0
        self.model = DeepSpeech(
            hidden_size=hparams.hidden_size,
            nb_layers=hparams.hidden_layers,
            vocab_size=hparams.vocab_size,
            input_feature_dim=hparams.audio_feature_dim,
            bidirectional=hparams.bidirectional,
        )

    def forward(self, inputs, input_sizes):
        return self.model(inputs, input_sizes)

    def decode(self, feature, feature_length, decode_type="greedy"):
        assert decode_type in ["greedy", "beam"]
        output = self.transformer.inference(
            feature, feature_length, decode_type=decode_type
        )
        return output

    def training_step(self, batch, batch_nb):

        inputs, targets, input_percentages, target_sizes = batch
        input_sizes = input_percentages.mul_(int(inputs.size(3))).int()

        out, output_sizes = self(inputs, input_sizes)

        prob = F.log_softmax(out, -1)
        ctc_loss = F.ctc_loss(
            prob.transpose(0, 1),
            targets,
            output_sizes,
            target_sizes,
            blank=BLANK_INDEX,
            zero_infinity=True,
        )

        loss = ctc_loss / out.size(0)  # average the loss by minibatch

        tqdm_dict = {"train-loss": loss}
        output = OrderedDict(
            {"loss": loss, "progress_bar": tqdm_dict, "log": tqdm_dict,}
        )
        return output

    def train_dataloader(self):
        dataloader = AudioDataLoader(
            train_dataset,
            num_workers=0,
            batch_size=3
            # batch_sampler=train_sampler # TODO: is lightning providing this?
        )
        return dataloader

    def configure_optimizers(self):
        optimizer = torch.optim.Adam(
            self.model.parameters(), lr=self.lr, weight_decay=1e-5
        )
        return optimizer

    @staticmethod
    def add_model_specific_args(parent_parser):
        parser = HyperOptArgumentParser(parents=[parent_parser])
        parser.add_argument("--num_encoder_layer", default=6, type=int)
        parser.add_argument("--lr", default=3e-4, type=float)
        parser.add_argument("--train_batch_size", default=20, type=int)
        parser.add_argument("--val_batch_size", default=20, type=int)
        return parser

def _collate_fn(batch):
    def func(p):
        return p[0].size(1)

    batch = sorted(batch, key=lambda sample: sample[0].size(1), reverse=True)
    longest_sample = max(batch, key=func)[0]
    freq_size = longest_sample.size(0)
    minibatch_size = len(batch)
    max_seqlength = longest_sample.size(1)
    inputs = torch.zeros(minibatch_size, 1, freq_size, max_seqlength)
    input_len_proportion = torch.FloatTensor(minibatch_size)
    target_sizes = torch.IntTensor(minibatch_size)
    targets = []
    for x in range(minibatch_size):
        sample = batch[x]
        tensor = sample[0]
        target = sample[1]
        seq_length = tensor.size(1)
        inputs[x][0].narrow(1, 0, seq_length).copy_(tensor)
        input_len_proportion[x] = seq_length / float(max_seqlength)
        target_sizes[x] = len(target)
        targets.append(torch.IntTensor(target))

    padded_target = pad_sequence(targets, batch_first=True)

    return inputs, padded_target, input_len_proportion, target_sizes


class AudioDataLoader(DataLoader):
    def __init__(self, *args, **kwargs):
        """
        Creates a data loader for AudioDatasets.
        """
        super().__init__(*args, **kwargs)
        self.collate_fn = _collate_fn

if __name__ == "__main__":

    HOME = os.environ["HOME"]
    asr_path = HOME + "/data/asr_data"
    raw_data_path = asr_path + "/ENGLISH/LibriSpeech"
    conf = DataConfig(LIBRI_VOCAB)
    audio_conf = AudioFeaturesConfig()
    train_samples = build_librispeech_corpus(raw_data_path, "debug", ["dev-clean"],)

    train_dataset = CharSTTDataset(train_samples, conf=conf, audio_conf=audio_conf,)
    vocab_size = len(train_dataset.char2idx)
    BLANK_INDEX = train_dataset.char2idx[BLANK_SYMBOL]
    audio_feature_dim = train_dataset.audio_fe.feature_dim

    litmodel = LitSTTModel(
        Params(
            hidden_size=64,
            hidden_layers=2,
            audio_feature_dim=audio_feature_dim,
            vocab_size=vocab_size,
        )
    )

    trainer = Trainer(
        logger=False,
        checkpoint_callback=False,
        max_epochs=3
    )
    trainer.fit(litmodel)
