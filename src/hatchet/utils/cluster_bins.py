from collections import Counter
import numpy as np
import pandas as pd

from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
from scipy.special import logsumexp
from scipy.spatial.distance import pdist, squareform
from hmmlearn import hmm

from hatchet.utils.ArgParsing import parse_cluster_bins_args
import hatchet.utils.Supporting as sp


def main(args=None):
    sp.log(msg='# Parsing and checking input arguments\n', level='STEP')
    args = parse_cluster_bins_args(args)
    sp.logArgs(args, 80)

    sp.log(msg='# Reading the combined BB file\n', level='STEP')
    tracks, bb, sample_labels, chr_labels = read_bb(args['bbfile'])

    if args['exactK'] > 0:
        minK = args['exactK']
        maxK = args['exactK']
    else:
        minK = args['minK']
        maxK = args['maxK']

        if minK <= 1:
            sp.log(
                msg='# WARNING: model selection does not support comparing K=1 to K>1. K=1 will be ignored.\n',
                level='WARNING',
            )

    if args['exactK'] > 0 and args['exactK'] == 1:
        sp.log(
            msg='# Found exactK=1, returning trivial clustering.\n',
            level='STEP',
        )
        best_labels = [1] * int(len(bb) / len(sample_labels))
    else:
        sp.log(
            msg='# Clustering bins by RD and BAF across tumor samples using locality\n',
            level='STEP',
        )
        (best_score, best_model, best_labels, best_K, results,) = hmm_model_select(
            tracks,
            minK=minK,
            maxK=maxK,
            seed=args['seed'],
            covar=args['covar'],
            decode_alg=args['decoding'],
            tmat=args['transmat'],
            tau=args['tau'],
        )

    best_labels = reindex(best_labels)
    bb['CLUSTER'] = np.repeat(best_labels, len(sample_labels))

    sp.log(msg='# Checking consistency of results\n', level='STEP')
    pivot_check = bb.pivot(index=['#CHR', 'START', 'END'], columns='SAMPLE', values='CLUSTER')
    # Verify that the array lengths and order match the bins in the BB file
    chr_idx = 0
    bin_indices = pivot_check.index.to_numpy()
    i = 0
    while chr_idx < len(tracks):
        my_chr = chr_labels[chr_idx][:-2]

        start_row = bin_indices[i]
        assert str(start_row[0]) == my_chr, (start_row[0], my_chr)

        prev_end = start_row[-1]

        start_idx = i
        i += 1
        while i < len(bin_indices) and bin_indices[i][0] == start_row[0] and bin_indices[i][1] == prev_end:
            prev_end = bin_indices[i][2]
            i += 1

        # check the array lengths
        assert tracks[chr_idx].shape[1] == i - start_idx, (
            tracks[chr_idx].shape[1],
            i - start_idx,
        )

        chr_idx += 1

    # Verify that cluster labels were applied correctly
    cl_check = pivot_check.to_numpy().T
    assert np.all(cl_check == cl_check[0])

    sp.log(msg='# Writing output\n', level='STEP')
    bb = bb[
        [
            '#CHR',
            'START',
            'END',
            'SAMPLE',
            'RD',
            '#SNPS',
            'COV',
            'ALPHA',
            'BETA',
            'BAF',
            'CLUSTER',
        ]
    ]
    bb.to_csv(args['outbins'], index=False, sep='\t')

    seg = form_seg(bb, args['diploidbaf'])
    seg.to_csv(args['outsegments'], index=False, sep='\t')

    sp.log(msg='# Done\n', level='STEP')


def read_bb(bbfile, use_chr=True, compressed=False):
    """
    Constructs arrays to represent the bin in each chromosome or arm.
    If bbfile was binned around chromosome arm, then uses chromosome arms.
    Otherwise, uses chromosomes.

    Returns:
        botht: list of np.ndarrays of size (n_bins, n_tracks)
            where n_tracks = n_samples * 2
        bb: table read from input bbfile
        sample_labels: order in which samples are represented in each array in botht
        chr_lables: order in which chromosomes or arms are represented in botht

    each array contains
    1 track per sample for a single chromosome arm.
    """

    bb = pd.read_table(bbfile)

    tracks = []

    sample_labels = []
    populated_labels = False

    chr_labels = []
    for ch, df0 in bb.groupby(['#CHR']):
        df0 = df0.sort_values('START')

        p_arrs = []
        q_arrs = []

        for sample, df in df0.groupby('SAMPLE'):
            if not populated_labels:
                sample_labels.append(sample)

            gaps = np.where(df.START.to_numpy()[1:] - df.END.to_numpy()[:-1] > 0)[0]
            # print(ch, gaps)

            if len(gaps) > 0:
                assert len(gaps) == 1, 'Found a chromosome with >1 gaps between bins'
                gap = gaps[0] + 1

                df_p = df.iloc[:gap]
                df_q = df.iloc[gap:]

                p_arrs.append(df_p.BAF.to_numpy())
                p_arrs.append(df_p.RD.to_numpy())

                q_arrs.append(df_q.BAF.to_numpy())
                q_arrs.append(df_q.RD.to_numpy())
            else:
                df_p = df
                p_arrs.append(df_p.BAF.to_numpy())
                p_arrs.append(df_p.RD.to_numpy())

        if len(q_arrs) > 0:
            tracks.append(np.array(p_arrs))
            chr_labels.append(str(ch) + '_p')

            tracks.append(np.array(q_arrs))
            chr_labels.append(str(ch) + '_q')
        else:
            tracks.append(np.array(p_arrs))
            chr_labels.append(str(ch) + '_p')

        populated_labels = True

    return (
        tracks,
        bb.sort_values(by=['#CHR', 'START', 'SAMPLE']),
        sample_labels,
        chr_labels,
    )


def hmm_model_select(
    tracks,
    minK=20,
    maxK=50,
    tau=10e-6,
    tmat='diag',
    decode_alg='viterbi',
    covar='diag',
    seed=0,
):
    assert tmat in ['fixed', 'diag', 'free']
    assert decode_alg in ['map', 'viterbi']

    # format input
    tracks = [a for a in tracks if a.shape[0] > 0 and a.shape[1] > 0]
    if len(tracks) > 1:
        X = np.concatenate(tracks, axis=1).T
        lengths = [a.shape[1] for a in tracks]
    else:
        X = tracks[0].T
        lengths = [tracks[0].shape[1]]

    best_K = 0
    best_score = 0
    best_model = None
    best_labels = None

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    C = squareform(pdist(X_scaled))

    rs = {}
    for K in range(minK, maxK + 1):
        # print(K, datetime.now())
        # construct initial transition matrix
        A = make_transmat(1 - tau, K)

        if tmat == 'fixed':
            model = hmm.GaussianHMM(
                n_components=K,
                init_params='mc',
                params='smc',
                covariance_type=covar,
                random_state=0,
            )
        elif tmat == 'free':
            model = hmm.GaussianHMM(
                n_components=K,
                init_params='mc',
                params='smct',
                covariance_type=covar,
                random_state=0,
            )
        else:
            model = DiagGHMM(
                n_components=K,
                init_params='mc',
                params='smct',
                covariance_type=covar,
                random_state=0,
            )

        model.startprob_ = np.ones(K) / K
        model.transmat_ = A
        model.fit(X, lengths)

        prob, labels = model.decode(X, lengths, algorithm=decode_alg)
        score = silhouette_score(C, labels, metric='precomputed')

        rs[K] = prob, score, labels
        if score > best_score:
            best_score = score
            best_model = model
            best_labels = labels
            best_K = K

    return best_score, best_model, best_labels, best_K, rs


class DiagGHMM(hmm.GaussianHMM):
    def _accumulate_sufficient_statistics(self, stats, obs, framelogprob, posteriors, fwdlattice, bwdlattice):
        super()._accumulate_sufficient_statistics(stats, obs, framelogprob, posteriors, fwdlattice, bwdlattice)

        if 't' in self.params:
            # for each ij, recover sum_t xi_ij from the inferred transition matrix
            bothlattice = fwdlattice + bwdlattice
            loggamma = (bothlattice.T - logsumexp(bothlattice, axis=1)).T

            # denominator for each ij is the sum of gammas over i
            denoms = np.sum(np.exp(loggamma), axis=0)
            # transpose to perform row-wise multiplication
            stats['denoms'] = denoms

    def _do_mstep(self, stats):
        super()._do_mstep(stats)
        if 't' in self.params:

            denoms = stats['denoms']
            x = (self.transmat_.T * denoms).T

            # numerator is the sum of ii elements
            num = np.sum(np.diag(x))
            # denominator is the sum of all elements
            denom = np.sum(x)

            # (this is the same as sum_i gamma_i)
            # assert np.isclose(denom, np.sum(denoms))

            stats['diag'] = num / denom
            # print(num.shape)
            # print(denom.shape)

            self.transmat_ = self.form_transition_matrix(stats['diag'])

    def form_transition_matrix(self, diag):
        tol = 1e-10
        diag = np.clip(diag, tol, 1 - tol)

        offdiag = (1 - diag) / (self.n_components - 1)
        transmat_ = np.diag([diag - offdiag] * self.n_components)
        transmat_ += offdiag
        # assert np.all(transmat_ > 0), (diag, offdiag, transmat_)
        return transmat_


def make_transmat(diag, K):
    offdiag = (1 - diag) / (K - 1)
    transmat_ = np.diag([diag - offdiag] * K)
    transmat_ += offdiag
    return transmat_


def reindex(labels):
    """
    Given a list of labels, reindex them as integers from 1 to n_labels
    Also orders them in nonincreasing order of prevalence
    """
    old2new = {}
    j = 1
    for i, _ in Counter(labels).most_common():
        old2new[i] = j
        j += 1
    old2newf = lambda x: old2new[x]

    return [old2newf(a) for a in labels]


def form_seg(bbc, balanced_threshold):
    segments = []
    for (key, sample), df in bbc.groupby(['CLUSTER', 'SAMPLE']):
        nbins = len(df)
        rd = df.RD.mean()
        nsnps = df['#SNPS'].sum()
        cov = df.COV.mean()
        a = np.sum(np.minimum(df.ALPHA, df.BETA))
        b = np.sum(np.maximum(df.ALPHA, df.BETA))
        baf = a / (a + b)
        baf = baf if (0.5 - baf) > balanced_threshold else 0.5
        segments.append([key, sample, nbins, rd, nsnps, cov, a, b, baf])
    seg = pd.DataFrame(
        segments,
        columns=[
            '#ID',
            'SAMPLE',
            '#BINS',
            'RD',
            '#SNPS',
            'COV',
            'ALPHA',
            'BETA',
            'BAF',
        ],
    )
    return seg


if __name__ == '__main__':
    main()
