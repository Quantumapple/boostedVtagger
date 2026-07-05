import argparse
import re

import matplotlib.pyplot as plt
import mplhep as hep

hep.style.use('CMS')


def parse_log(log_path):
    text = open(log_path).read()
    train = re.findall(r'Train AvgLoss: ([\d.]+), AvgAcc: ([\d.]+)', text)
    val = re.findall(r'Epoch #(\d+): Current validation metric: ([\d.]+) \(best: ([\d.]+)\)', text)

    epochs = [int(e) for e, _, _ in val]
    train_loss = [float(loss) for loss, _ in train]
    train_acc = [float(acc) for _, acc in train]
    val_acc = [float(acc) for _, acc, _ in val]
    best_acc = [float(best) for _, _, best in val]

    assert len(epochs) == len(train_loss) == len(train_acc), \
        'Mismatched number of train/val log entries -- check the log file is from a single, complete run.'

    return epochs, train_loss, train_acc, val_acc, best_acc


def main():
    parser = argparse.ArgumentParser(description='Plot MLP training curves (loss/accuracy vs epoch) '
                                      'in CMS style from a weaver train.py log file.')
    parser.add_argument('--log_file')
    parser.add_argument('--output', default='training_curves.png')
    parser.add_argument('--cms-label', default='Preliminary')
    args = parser.parse_args()

    epochs, train_loss, train_acc, val_acc, best_acc = parse_log(args.log_file)
    best_epoch = epochs[max(range(len(val_acc)), key=lambda i: val_acc[i])]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 9), sharex=True)

    ax1.plot(epochs, train_loss, marker='o', color='#5790fc', label='Train')
    ax1.set_xlim(-1, 30)
    ax1.set_xlabel('Epoch')
    ax1.set_ylabel('Loss')
    hep.cms.label(args.cms_label, ax=ax1, fontsize=20, rlabel='')

    ax2.plot(epochs, train_acc, marker='o', color='#5790fc', label='Train')
    ax2.plot(epochs, val_acc, marker='s', color='#e42536', label='Validation')
    ax2.axvline(best_epoch, color='gray', linestyle='--', linewidth=1, label=f'Best epoch ({best_epoch})')
    ax2.set_xlabel('Epoch')
    ax2.set_ylabel('Accuracy')
    ax2.legend(loc='best')
    hep.cms.label(args.cms_label, ax=ax2, fontsize=20, rlabel='')

    plt.tight_layout()
    plt.savefig(args.output, dpi=150)
    print(f'Saved {args.output}')
    print(f'Best epoch: {best_epoch}, val acc: {max(val_acc):.5f}')


if __name__ == '__main__':
    main()
