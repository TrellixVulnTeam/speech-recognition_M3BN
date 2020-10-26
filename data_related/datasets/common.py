import torchaudio
from functools import partial

from tqdm import tqdm
from typing import Dict

from abc import abstractmethod

import wget
from pathlib import Path

import os
from util import data_io
from util.util_methods import process_with_threadpool, exec_command

from data_related.utils import unzip, Sample

import multiprocessing

num_cpus = multiprocessing.cpu_count()

MANIFEST_FILE = "manifest.jsonl.gz"

class SpeechCorpus:

    def __init__(self, name: str, url: str) -> None:
        super().__init__()
        self.url = url
        self.name = name

    def maybe_download(self, download_folder)->str:
        return maybe_download(self.name, download_folder, self.url)

    @staticmethod
    def extract_downloaded(raw_zipfile,extract_folder):
        unzip(raw_zipfile, extract_folder)

    @staticmethod
    def process_write_manifest(corpus_folder, file2utt):
        samples = tqdm(
            s._asdict()
            for s in process_with_threadpool(
                ({"audio_file": f, "text": t} for f, t in file2utt.items()),
                partial(convert_to_mp3_get_length, processed_folder=corpus_folder),
                max_workers=2 * num_cpus,
            )
        )
        data_io.write_jsonl(f"{corpus_folder}/{MANIFEST_FILE}", samples)

    @abstractmethod
    def build_audiofile2text(self, path) -> Dict[str, str]:
        raise NotImplementedError

def convert_to_mp3_get_length(audio_file, text, processed_folder) -> Sample:
    suffix = Path(audio_file).suffix
    mp3_file_name = audio_file.replace("/", "_").replace(suffix, ".mp3")

    while mp3_file_name.startswith("_"):
        mp3_file_name = mp3_file_name[1:]

    mp3_file = f"{processed_folder}/{mp3_file_name}"
    exec_command(f"sox {audio_file} {mp3_file}")

    si, ei = torchaudio.info(mp3_file)
    num_frames = si.duration / si.channels
    len_in_seconds = num_frames / si.rate

    return Sample(mp3_file_name, text, len_in_seconds, num_frames)

def maybe_download(data_set, download_folder, url):
    localfile = os.path.join(download_folder, data_set + Path(url).suffix)
    if not os.path.exists(localfile):
        print(f"downloading: {url}")
        wget.download(url, localfile)
    else:
        print(f"found: {localfile} no need to download")
    return localfile

