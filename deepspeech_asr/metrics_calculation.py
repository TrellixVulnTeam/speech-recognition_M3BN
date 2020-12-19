import Levenshtein
from typing import List, Tuple

"""
nemo is using [editdistance](https://github.com/roy-ht/editdistance)

here Levenshtein is used: https://github.com/ztane/python-Levenshtein/
"""


def calc_num_word_errors(hyp: str, ref: str) -> Tuple[int, int]:
    """
    based on: https://github.com/SeanNaren/deepspeech.pytorch/blob/master/deepspeech_pytorch/decoder.py
    https://github.com/SeanNaren/deepspeech.pytorch/blob/78f7fb791f42c44c8a46f10e79adad796399892b/deepspeech_pytorch/decoder.py#L42
    """

    def tokenize(s):
        return s.split()

    b = set(tokenize(hyp) + tokenize(ref))
    token2idx = {t: k for k, t in enumerate(b)}

    # map the words to a char array (Levenshtein packages only accepts
    # strings)
    w1 = [chr(token2idx[w]) for w in hyp.split()]
    w2 = [chr(token2idx[w]) for w in ref.split()]

    len_ref = len(ref.split(" "))
    return Levenshtein.distance("".join(w1), "".join(w2)), len_ref


def calc_num_char_erros(hyp: str, ref: str) -> Tuple[int, int]:
    """
    based on: https://github.com/SeanNaren/deepspeech.pytorch/blob/78f7fb791f42c44c8a46f10e79adad796399892b/deepspeech_pytorch/decoder.py#L62
    """
    hyp, ref, = (
        hyp.replace(" ", ""),
        ref.replace(" ", ""),
    )  # TODO(tilo): why removing spaces?

    len_ref = len(ref.replace(" ", ""))
    return Levenshtein.distance(hyp, ref), len_ref


def calc_wer(hypos: List[str], targets: List[str]):
    errors_lens = [calc_num_word_errors(hyp, ref) for hyp, ref in zip(hypos, targets)]
    return calc_rate(errors_lens)


def calc_cer(hypos: List[str], targets: List[str]):
    errors_lens = [calc_num_char_erros(hyp, ref) for hyp, ref in zip(hypos, targets)]
    return calc_rate(errors_lens)


def calc_rate(errors_lens):
    num_tokens = sum([l for _, l in errors_lens])
    errors = sum([s for s, _ in errors_lens])
    return float(errors) / float(num_tokens)
