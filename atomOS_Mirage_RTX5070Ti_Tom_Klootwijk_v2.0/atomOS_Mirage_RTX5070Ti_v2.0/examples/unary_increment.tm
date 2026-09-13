# Read head starts at the middle of a finite tape. Blank symbol is 0.
# Header: states COUNT halt HALT_STATE
states 2 halt 1
# state read write move next
0 1 1  1 0
0 0 1  0 1
