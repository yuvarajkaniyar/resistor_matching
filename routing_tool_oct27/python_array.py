def createArray(numRows, numCols, elements):
    """Create a 2D array (list of lists) from a flat list of elements."""
    arr = []
    idx = 0
    for i in range(numRows):
        row = []
        for j in range(numCols):
            row.append(elements[idx])
            idx += 1
        arr.append(row)
    return arr


def getAllUnique(arr):
    """Get all unique elements across the entire 2D array, preserving order."""
    result = []
    for row in arr:
        for elem in row:
            if elem not in result:
                result.append(elem)
    return result


def getPositions(arr, target):
    """Get list of (row, col) 1-based positions of target element."""
    result = []
    for rowIdx, row in enumerate(arr, start=1):
        for colIdx, elem in enumerate(row, start=1):
            if elem == target:
                result.append((rowIdx, colIdx))
    return result


def getCount(arr, target):
    """Get total count of target element in the array."""
    count = 0
    for row in arr:
        for elem in row:
            if elem == target:
                count += 1
    return count


def getUniqueInRow(arr, rowIdx):
    """Get unique elements in a specific row (1-based index)."""
    result = []
    for elem in arr[rowIdx - 1]:
        if elem not in result:
            result.append(elem)
    return result


def getUniqueInCol(arr, colIdx):
    """Get unique elements in a specific column (1-based index)."""
    result = []
    for row in arr:
        elem = row[colIdx - 1]
        if elem not in result:
            result.append(elem)
    return result


def getPos(arr, target):
    """Get 1-based position of first occurrence of target in a flat list."""
    for i, elem in enumerate(arr, start=1):
        if elem == target:
            return i
    return None


def getnextPos_in_row(arr, row, target, col):
    """Get next 1-based column position of target in a row, after given column.
    Returns 0 if not found."""
    rowList = arr[row - 1]
    for i in range(col, len(rowList)):  # i is 0-based index, starts at 'col' (next after 1-based 'col')
        if rowList[i] == target:
            return i + 1  # convert back to 1-based
    return 0


def getCountInRow(arr, rowIdx, target):
    """Get count of target element in a specific row (1-based index)."""
    row = arr[rowIdx - 1]
    return sum(1 for elem in row if elem == target)


def getElement(arr, m, n):
    """Get element at position (m, n) using 1-based indices."""
    return arr[m - 1][n - 1]

def getFirstPosInRow(arr, row, target):
    """Get first 1-based column position of target in a given row (1-based index).
    Returns 0 if not found."""
    rowList = arr[row - 1]
    for i, elem in enumerate(rowList, start=1):
        if elem == target:
            return i
    return 0

def getprevPos_in_row(arr, row, target, col):
    """Get previous 1-based column position of target in a row, before given column.
    Returns 0 if not found."""
    rowList = arr[row -1]
    for i in range(col - 2, -1, -1):  # i is 0-based index, starts just before 'col' (1-based)
        if rowList[i] == target:
            return i + 1  # convert back to 1-based
    return 0

def near_element(arr, row, col, direction):
    """Get the element near (row, col) in the given direction.
    direction: 'up', 'down', 'left', 'right' (1-based row, col).
    up -> row+1, same col
    down -> row-1, same col
    left -> same row, col-1
    right -> same row, col+1
    Returns None if out of bounds."""
    numRows = len(arr)
    numCols = len(arr[0]) if numRows > 0 else 0

    if direction == "up":
        newRow, newCol = row + 1, col
    elif direction == "down":
        newRow, newCol = row - 1, col
    elif direction == "left":
        newRow, newCol = row, col - 1
    elif direction == "right":
        newRow, newCol = row, col + 1
    else:
        raise ValueError("direction must be 'up', 'down', 'left', or 'right'")

    if 1 <= newRow <= numRows and 1 <= newCol <= numCols:
        return arr[newRow - 1][newCol - 1]
    return None

def edge_element_column(arr, element, row, from_right=True):
    """
    Get the edge column position of an element in a given row (1-based).

    Parameters:
        arr       : 2D array
        element   : target element to search for
        row       : 1-based row index
        from_right: if True, returns the last (rightmost) column position
                    if False, returns the first (leftmost) column position

    Returns:
        1-based column index, or 0 if element not found in the row.
    """
    # Guard: if row is out of bounds, return 0 instead of crashing
    if row < 1 or row > len(arr):
        return 0

    rowList = arr[row - 1]

    if from_right:
        for i in range(len(rowList) - 1, -1, -1):
            if rowList[i] == element:
                return i + 1
    else:
        for i in range(len(rowList)):
            if rowList[i] == element:
                return i + 1

    return 0

"""
arr = createArray(3, 3, ["A","B","C","B","C","A","C","A","B"])
print(arr)                      # [['A','B','C'], ['B','C','A'], ['C','A','B']]
print(getAllUnique(arr))        # ['A', 'B', 'C']
print(getPositions(arr, "A"))   # [(1,1), (2,3), (3,2)]
print(getCount(arr, "A"))       # 3
print(getUniqueInRow(arr, 1))   # ['A', 'B', 'C']
print(getUniqueInCol(arr, 1))   # ['A', 'B', 'C']
print(getElement(arr, 2, 2))    # 'C'
"""