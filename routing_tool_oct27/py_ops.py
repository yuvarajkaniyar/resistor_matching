from functools import cmp_to_key

def sort_pairs(pairs):
    """
    Sorts a list of pairs [x1, x2] based on:
    - Priority 1 (n): n2 lies between m1 and m2  → n comes first
    - Priority 2 (m): m2 lies between n1 and n2  → m comes first
    - Tie-break    : compare second elements directly
    """
    def compare(n, m):
        n1, n2 = n
        m1, m2 = m

        n_in_m_range = min(m1, m2) < n2 < max(m1, m2)  # n2 between m1 & m2
        m_in_n_range = min(n1, n2) < m2 < max(n1, n2)  # m2 between n1 & n2

        if n_in_m_range and not m_in_n_range:
            return -1   # n has priority → comes first
        elif m_in_n_range and not n_in_m_range:
            return 1    # m has priority → comes first
        else:
            return (n2 > m2) - (n2 < m2)  # Tie-break by second element

    return sorted(pairs, key=cmp_to_key(compare))


# ── Example Usage ──────────────────────────────────────────────
pairs = [[1, 7], [5, 3], [2, 9], [6, 4]]
result = sort_pairs(pairs)
print("Sorted:", result)