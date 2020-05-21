import os
from typing import NamedTuple

import pytorch_lightning as pl
from test_tube import HyperOptArgumentParser
from collections import OrderedDict
import torch as t
import numpy as np
import torch.nn.functional as F
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
            prob.transpose(0, 1), targets, input_sizes, output_sizes, blank=BLANK_INDEX, zero_infinity=True)

        loss = ctc_loss / out.size(0)  # average the loss by minibatch

        tqdm_dict = {
            "train-loss": loss,
        }
        output = OrderedDict(
            {
                "loss": loss,
                "progress_bar": tqdm_dict,
                "log": tqdm_dict,
            }
        )
        return output

    def train_dataloader(self):
        # dataloader = build_multi_dataloader(
        #     record_root='data/tfrecords/{}.tfrecord',
        #     index_root='data/tfrecord_index/{}.index',
        #     data_name_list=[
        #         # 'magic_data_train_562694',
        #         'data_aishell_train_117346',
        #         # 'c_500_train_549679',
        #         # 'ce_200_161001'
        #     ],
        #     batch_size=self.hparams.train_batch_size,
        #     num_workers=self.hparams.train_loader_num_workers
        # )
        dataloader = build_raw_data_loader(
            [
                # 'data/filterd_manifest/ce_200.csv',
                data_path + "/lightning_manifests/train-clean-100.csv",
                data_path + "/lightning_manifests/train-clean-360.csv",
                data_path + "/lightning_manifests/train-other-500.csv",
                # 'data/filterd_manifest/c_500_train.csv',
                # 'data/filterd_manifest/aidatatang_200zh_train.csv',
                # 'data/filterd_manifest/data_aishell_train.csv',
                # 'data/filterd_manifest/AISHELL-2.csv',
                # 'data/filterd_manifest/magic_data_train.csv',
                # 'data/manifest/libri_100.csv',
                # 'data/manifest/libri_360.csv',
                # 'data/manifest/libri_500.csv'
            ],
            vocab_path=self.hparams.vocab_path,
            batch_size=self.hparams.train_batch_size,
            num_workers=self.hparams.train_loader_num_workers,
            speed_perturb=True,
            max_duration=15,
        )
        return dataloader

    def optimizer_step(
        self, epoch_nb, batch_nb, optimizer, optimizer_i, second_order_closure=None
    ):
        lr = self.hparams.factor * (
            (self.hparams.model_size ** -0.5)
            * min(
                (self.global_step + 1) ** -0.5,
                (self.global_step + 1) * (self.hparams.warm_up_step ** -1.5),
            )
        )
        self.lr = lr
        for pg in optimizer.param_groups:
            pg["lr"] = lr
        optimizer.step()
        optimizer.zero_grad()

    def configure_optimizers(self):
        optimizer = AdamW(self.parameters(), lr=self.hparams.lr, betas=(0.9, 0.997))
        optimizer = Lookahead(optimizer)
        return optimizer

    @staticmethod
    def add_model_specific_args(parent_parser):
        parser = HyperOptArgumentParser(parents=[parent_parser])
        parser.add_argument("--num_freq_mask", default=2, type=int)
        parser.add_argument("--num_time_mask", default=2, type=int)
        parser.add_argument("--freq_mask_length", default=30, type=int)
        parser.add_argument("--time_mask_length", default=20, type=int)
        parser.add_argument("--feature_dim", default=400, type=int)
        parser.add_argument("--model_size", default=512, type=int)
        parser.add_argument("--feed_forward_size", default=2048, type=int)
        parser.add_argument("--hidden_size", default=64, type=int)
        parser.add_argument("--dropout", default=0.1, type=float)
        parser.add_argument("--num_head", default=8, type=int)
        parser.add_argument("--num_encoder_layer", default=6, type=int)
        parser.add_argument("--num_decoder_layer", default=6, type=int)
        parser.add_argument(
            "--vocab_path",
            default=data_path + "/lightning_corpus/librispeech.model",
            type=str,
        )
        parser.add_argument("--max_feature_length", default=1024, type=int)
        parser.add_argument("--max_token_length", default=50, type=int)
        parser.add_argument("--share_weight", default=True, type=bool)
        parser.add_argument("--loss_lambda", default=0.8, type=float)
        parser.add_argument("--smoothing", default=0.1, type=float)

        parser.add_argument("--lr", default=3e-4, type=float)
        parser.add_argument("--warm_up_step", default=16000, type=int)
        parser.add_argument("--factor", default=1, type=int)
        parser.add_argument("--enable_spec_augment", default=True, type=bool)

        parser.add_argument("--train_batch_size", default=20, type=int)
        parser.add_argument("--train_loader_num_workers", default=8, type=int)
        parser.add_argument("--val_batch_size", default=20, type=int)
        parser.add_argument("--val_loader_num_workers", default=8, type=int)

        return parser


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
