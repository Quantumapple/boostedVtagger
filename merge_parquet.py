import json
import argparse
import re
import pandas as pd
from pathlib import Path
from tqdm import tqdm

def natural_key(text):
    """
    Splits text into a list of strings and integers.
    e.g., "item10" -> ["item", 10]
    """
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]

def merge_by_sample_key(input_path, pattern):

    files = Path(input_path).glob(f'*{pattern}*')

    if len(files) == 0:
        print('No input files found.')
        return pd.DataFrame()

    files.sort(key=natural_key)

    dfs = []
    for ifile in files:
        dfs.append(pd.read_parquet(ifile))

    df = pd.concat(dfs, ignore_index=True)

    return df

## --------------------------------------
if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Submit condor jobs to pre-process V-jet tagger data')

    parser.add_argument(
        '-d',
        '--inputdir',
        metavar = 'PATH',
        type = str,
        help = 'Path to input directory',
        required = True,
        dest = 'inputdir',
    )

    parser.add_argument(
        '-s',
        '--sample',
        metavar = 'JSONFILE',
        type = str,
        help = 'input json file including dataset',
        required = True,
        dest = 'sample',
    )

    parser.add_argument(
        '-y',
        '--year',
        metavar = 'YEAR',
        help = 'year',
        type = str,
        default = '2024',
        dest = 'year',
    )

    args = parser.parse_args()

    ## Make directory for output
    name = Path(args.inputdir).name
    outdir = Path(f'merged_{name}')
    outdir.mkdir(parents=True, exist_ok=True)

    ## Extract keys
    ## JSON data tier
    ## year - process name - separated process name
    with open(args.sample, 'r') as file:
        samples = json.load(file)

    year_data = samples.get(args.year, {})

    sample_keys = []
    for key in year_data.keys():
        sample_keys += list(year_data[key].keys())

    for isample in tqdm(sample_keys, desc="Processing samples"):
        df = merge_by_sample_key(args.inputdir, isample)
        df.to_parquet(outdir / f'{isample}.parquet')