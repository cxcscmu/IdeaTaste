"""Level 1, literature selection: citation matching and citation diversity (paper Sec. 3.2.1).

Every citation set is a set of corpus ids. Documents with an empty set stay in every denominator and contribute zero.
"""

import numpy as np
from scipy.sparse import csr_matrix

BLOCK_ROWS = 256


def _incidence(citation_sets, column_of):
    indptr, columns = [0], []
    for citations in citation_sets:
        columns.extend(column_of[paper_id] for paper_id in citations)
        indptr.append(len(columns))
    return csr_matrix((np.ones(len(columns), np.float32), np.array(columns, np.int64), np.array(indptr, np.int64)), shape=(len(citation_sets), len(column_of)))


def _nearest_jaccard(row_sets, column_sets):
    """For J(row, column) = |∩| / |∪|: best match of every row and of every column."""
    vocabulary = sorted(set().union(*row_sets, *column_sets))
    column_of = {paper_id: k for k, paper_id in enumerate(vocabulary)}
    rows, columns = _incidence(row_sets, column_of), _incidence(column_sets, column_of)
    row_sizes = np.asarray(rows.sum(axis=1)).ravel()
    column_sizes = np.asarray(columns.sum(axis=1)).ravel()
    columns_t = columns.T.tocsc()
    best_of_row = np.zeros(len(row_sets))
    best_of_column = np.zeros(len(column_sets))
    for start in range(0, len(row_sets), BLOCK_ROWS):
        stop = min(start + BLOCK_ROWS, len(row_sets))
        intersection = np.asarray((rows[start:stop] @ columns_t).todense(), dtype=np.float64)
        union = row_sizes[start:stop, None] + column_sizes[None, :] - intersection
        jaccard = np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)
        best_of_row[start:stop] = jaccard.max(axis=1)
        np.maximum(best_of_column, jaccard.max(axis=0), out=best_of_column)
    return best_of_row, best_of_column


def match_cite(reference_sets, proposal_sets):
    """M_cite = harmonic mean of J_{A->H} and J_{H->A} (Eq. 1)."""
    best_of_paper, best_of_proposal = _nearest_jaccard(reference_sets, proposal_sets)
    proposal_to_reference = float(best_of_proposal.mean())  # J_{A->H}
    reference_to_proposal = float(best_of_paper.mean())  # J_{H->A}
    total = proposal_to_reference + reference_to_proposal
    return 2 * proposal_to_reference * reference_to_proposal / total if total > 0 else 0.0


def citation_threshold(reference_sets):
    """tau: the mean citation-set size of the area's human papers (Appendix C.1)."""
    return float(np.mean([len(citations) for citations in reference_sets]))


def diversity_cite(citation_sets, tau):
    """D_cite = Q * S with sufficiency Q and spread S (Eq. 2)."""
    sizes = [len(citations) for citations in citation_sets]
    total = sum(sizes)
    sufficiency = float(np.mean([min(size / tau, 1.0) for size in sizes]))
    spread = len(set().union(*citation_sets)) / total if total else 0.0
    return sufficiency * spread
