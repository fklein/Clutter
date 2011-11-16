#!/usr/bin/env python3

__author__ = "Florian Klein <ueberjesus-at-gmail-dot-com>"
__all__ = ['Board', 'TicTacToe', 'Player', 'AiPlayer', 'ConsolePlayer', 'CallbackHandler']
__doc__ = """A module implementing the game Tic Tac Toe.

The module implements the game in an object oriented fashion.
The module also features an advanced computer opponent that supports
different difficulty levels ranging from "very simple" to "the perfect player".

If the module is started as a standalone programm, it will run a console
based version of the game. The module can however also be imported as an 
API to created customized versions of the game. The data model behind the game,
the game rules and a computer controlled player are all included in the module.
All that has to be done is to subclass the "Player" class to interact with a
player.

>>> from tictactoe import *
>>> p1 = AiPlayer('X', level=7)
>>> p2 = ConsolePlayer('O', name="Human")
>>> game = TicTacToe(p1, p2)
>>> game.play()
...
>>> game.get_winner()
...
>>> print(game.board)
...

"""

from abc import ABCMeta, abstractmethod
import random, itertools

class Board(object):
    """A simple board for the game Tic Tac Toe.

    The boards data is accessible in a list-like fashion. Every cell on
    the board's grid has a unique index assigned to it.
    The following figure illustrates the cell-to-index mapping:

       |   |
     6 | 7 | 8
    ---+---+---
     3 | 4 | 5
    ---+---+---
     0 | 1 | 2
       |   |

    The object itself basically behaves like a list:

    >>> b = tic.Board()
    >>> b[2] == None
    True
    >>> b[2] = 'X'
    >>> b[2]
    'X'

    However only a subset of list operations is supported.
    You can only assign the value 'X', 'O' and None to the cells.

    """
    _BOARDYMBOLS = ['X', 'O', None]
    _ROWS = [
        [0, 1, 2], [3, 4, 5], [6, 7, 8],  # Horizontal
        [0, 3, 6], [1, 4, 7], [2, 5, 8],  # Vertical
        [0, 4, 8], [2, 4, 6]              # Diagonal
    ]

    def __init__(self, *values):
        """Initialize a new Board object.

        If no arguments are specified, an empty board is initialized
        (all cells are "None"). It's also possible to specify the initial
        value for each cell. In this case the values for all nine cells
        have to be passed to the constructor.

        """
        self._cells = []
        if len(values) < 1:
            for i in range(9):
                self._cells.append(None)
        elif len(values) == 9:
            for value in values:
                if value in Board._BOARDYMBOLS:
                    self._cells.append(value)
                else:
                    raise ValueError('"{0}" is not a valid board symbol'.format(value))
        else:
            raise ValueError("You must specify a value for each of the board's cells.")

    def __getitem__(self, index):
        """Return a cell's value."""
        return self._cells[index]

    def __setitem__(self, index, value):
        """Set a cell's value."""
        if value in Board._BOARDYMBOLS:
            self._cells[index] = value
        else:
            raise ValueError('"{0}" is not a valid board symbol.'.format(value))

    def __iter__(self):
        """Return an iterator that iterates over the board's cells."""
        return iter(self._cells)

    def __str__(self):
        """Return a nice string representation of the board."""
        cells = list(map(lambda i: ' ' if i is None else i, self._cells))
        lines = [
            '   |   |   ',
            ' {6} | {7} | {8} '.format(*cells),
            '---+---+---',
            ' {3} | {4} | {5} '.format(*cells),
            '---+---+---',
            ' {0} | {1} | {2} '.format(*cells),
            '   |   |   ',
        ]
        return '\n'.join(lines)

    def __repr__(self):
        """Return a simple string representation of the board."""
        args = map(lambda i: 'None' if i is None else "'{0}'".format(i), self._cells)
        return 'Board({0})'.format(', '.join(args))

    def winner(self):
        """Return the winner ('X' or 'O') if one player has won or 'None' otherwise."""
        for a, b, c in Board._ROWS:
            if (self._cells[a] != None
                and self._cells[a] == self._cells[b] == self._cells[c]):
                return self._cells[a]
        return None

    def get_cells(self, symbol):
        """Return the indices of all cells that match the symbol specified."""
        cells = []
        indexes = range(len(self._cells))
        for index, item in zip(indexes, self._cells):
            if item == symbol:
                cells.append(index)
        return tuple(cells)

    def get_free_cells(self):
        """Return the indices of all free cells."""
        return self.get_cells(None)

    def get_X_cells(self):
        """Return the indices of all cells occupied by Player 'X'."""
        return self.get_cells('X')

    def get_O_cells(self):
        """Return the indices of all cells occupied by Player 'O'."""
        return self.get_cells('O')

    def find_rows_permutated(self, values):
        """Search for rows that contain the values specified in any order.

        The result is list of all rows (the row's cell indices) that contain
        the specified values in any permutation. The list of values passed
        to the method has to contain exactly three items.

        >>> b = Board('O', None, 'X', None, 'O', None, None, 'X', 'X')
        >>> print(b)
           |   |
           | X | X
        ---+---+---
           | O |
        ---+---+---
         O |   | X
           |   |
        >>> b.find_rows_permutated(['X','X',None])
        [[6, 7, 8], [2, 5, 8]]

        """
        if len(values) != 3:
            raise ValueError("Need exactly 3 values.")
        a, b, c = values
        permutations = [
            [a, b, c], [a, c, b],
            [b, a, c], [b, c, a],
            [c, a, b], [c, b, a],
        ]
        result = []
        for row in Board._ROWS:
            i, j, k = row
            for p in permutations:
                if self._cells[i] == p[0] and self._cells[j] == p[1] and self._cells[k] == p[2]:
                    result.append(row[:])
                    break
        return result

    def find_rows_exact(self, values):
        """Search for rows that contain the values specified in exactly that order.

        The result is list of all rows (the row's cell indices) that contain
        the specified values in exactly that order. The rows will be returned
        in a matching fashion. row[0], row[1], at row[2]
        The list of values passed to the method has to contain exactly three items.

        >>> b = Board('O', None, 'X', None, 'O', None, None, 'X', 'X')
        >>> print(b)
           |   |
           | X | X
        ---+---+---
           | O |
        ---+---+---
         O |   | X
           |   |
        >>> b.find_rows_exact(['X','X',None])
        [[8, 7, 6]]

        """
        cells = self._cells
        if len(values) != 3:
            raise ValueError("Need exactly 3 values.")
        a, b, c = values
        result = []
        for row in Board._ROWS:
            # Check rows forward...
            i, j, k = row
            if cells[i] == a and cells[j] == b and cells[k] == c:
                result.append(row[:])
            # ...and backwards
            i, j, k = row[::-1]
            if cells[i] == a and cells[j] == b and cells[k] == c:
                result.append(row[::-1])
        return result


class Player(object, metaclass=ABCMeta):
    """An abstract player for the game.

    This class can be subclassed to created an arbitrary player for
    the Tic Tac Toe game. Subclasses must provide a method "make_move".
    A Players symbol can be either "X" or "O".

    """

    def __init__(self, symbol):
        """Initialize the new player."""
        if symbol not in ['X', 'O']:
            raise ValueError('Invalid player symbol. Must be either "X" or "O".')
        self.symbol = symbol

    def __str__(self):
        """Return a nice string representation of the player."""
        return "Player {0}".format(self.symbol)

    @abstractmethod
    def make_move(self, board):
        """Determine a (free) cell on the board and move there.

        This is the core method of the player object that needs to be overriden in
        subclasses. This should let the player chose a free cell on the board
        (for example by evaluating user input) and subsequently move to that cell
        (i.e. place the players symbol there). The cell's index that the player has
        moved to is then returned.

        """
        pass


class PlayerAbortException(Exception):
    """A simple Exception to signal that a player aborts his move."""
    pass


class AiPlayer(Player):
    """A computer controlled player for the game Tic Tac Toe.

    The players difficulty level can be chosen from a range of 1 (very easy, random moves)
    to 9 (perfect player, will *NEVER* lose). The algorithm follows this basic strategy:

        1) WIN: If player has two in a row and the third cell on that row is empty,
           move to that cell, to get three in a row.
        2) BLOCK: If opponent has two in a row and the third cell on that row is empty,
           move to that cell, blocking the opponent from winning.
        3) FORK: Move to any cell that gives the player two in a row on two or more
           rows (thus creating a situation in which the player can win in two ways).
        4) BLOCK FORK: If the opponent has the possibility to fork, block him:
           a) FORCE DEFENSE: Force the opponent into defending by getting two in a row.
              However the remaining free cell can not be one of the opponent's fork
              possibilities, as this would give the opponent the ability to defend
              AND fork at the same time.
           b) BLOCK MOVE: Move to the cell, blocking the opponent. Obviously this 
              does not work if the opponent has multiple ways to fork.
        5) CENTER: Move to the center.
        6) OPPOSITE CORNER: If the opponent is in a corner, move to the cell on
           the opposite corner.
        7) EMPTY CORNER: Move to any empty corner.
        8) RANDOM: Choose a random free cell

    The highest possible move from this list will be selected and executed.
    See: http://en.wikipedia.org/wiki/Tic-tac-toe#Strategy

    """
    def __init__(self, symbol, level=6):
        """Initialize the new player."""
        super(AiPlayer, self).__init__(symbol)
        if level > 9 or level < 1:
            raise ValueError('The difficulty level must be a value between 1 and 9.')
        self.level = level

    def make_move(self, board):
        """Determine the next move and execute it."""
        move = self.next_move(board)
        if not move is None:
            board[move] = self.symbol
        else:
            raise PlayerAbortException("None move found.")
        return move

    def next_move(self, board):
        """Calculate the player's next move based on the diffculty level.

        The method returns the index of the cell  for the next move.
        As the algorithm incorporates some randomization the value returned
        is not neccessarily the same every time the method is called.

        """
        difficulty = {
            1: [self.move_random],
            2: [self.move_winning,
                self.move_random],
            3: [self.move_winning,
                self.move_blocking,
                self.move_random],
            4: [self.move_winning,
                self.move_blocking,
                self.move_free_corner,
                self.move_random],
            5: [self.move_winning,
                self.move_blocking,
                self.move_opposite_corner,
                self.move_random],
            6: [self.move_winning,
                self.move_blocking,
                self.move_opposite_corner,
                self.move_free_corner,
                self.move_random],
            7: [self.move_winning,
                self.move_blocking,
                self.move_center,
                self.move_opposite_corner,
                self.move_free_corner,
                self.move_random],
            8: [self.move_winning,
                self.move_blocking,
                self.move_fork,
                self.move_center,
                self.move_opposite_corner,
                self.move_free_corner,
                self.move_random],
            9: [self.move_winning,
                self.move_blocking,
                self.move_fork,
                self.move_block_fork,
                self.move_center,
                self.move_opposite_corner,
                self.move_free_corner,
                self.move_random],
        }
        # Call all defined functions for difficulty level until a valid move is found.
        for func in difficulty[self.level]:
            move = func(board)
            if move != None:
                return move
        return None

    def move_winning(self, board):
        """Return a move that let's the player win."""
        moves = self._moves_winning(board, self.symbol)
        if len(moves) > 0:
            return random.choice(moves)
        return None

    def move_blocking(self, board):
        """Return a move that blocks the opponent from winning."""
        opponent_symbol = 'O'
        if self.symbol == 'O':
            opponent_symbol = 'X'
        moves = self._moves_winning(board, opponent_symbol)
        if len(moves) > 0:
            return random.choice(moves)
        return None

    def _moves_winning(self, board, symbol):
        """Return all moves that let's the player specified by the symbol win."""
        result = []
        for row in Board._ROWS:
            a, b, c = row
            if board[a] == None and board[b] == board[c] == symbol:
                result.append(a)
            if board[b] == None and board[a] == board[c] == symbol:
                result.append(b)
            if board[c] == None and board[a] == board[b] == symbol:
                result.append(c)
        return result

    def move_fork(self, board):
        """Return a move that creates a fork for the player."""
        forks = self._moves_fork(board, self.symbol)
        if len(forks) > 0:
            return random.choice(forks)
        return None

    def move_block_fork(self, board):
        """Return a move that blocks the opponent from creating a fork."""
        opponent_symbol = 'O'
        if self.symbol == 'O':
            opponent_symbol = 'X'
        forks = self._moves_fork(board, opponent_symbol)
        forceblock = []
        if len(forks) <= 0:
            return None
        for row in Board._ROWS:
            a, b, c = row
            if board[a] == board[b] == None and board[c] == self.symbol:
                if b not in forks:
                    forceblock.append(a)
                if a not in forks:
                    forceblock.append(b)
            if board[a] == board[c] == None and board[b] == self.symbol:
                if c not in forks:
                    forceblock.append(a)
                if a not in forks:
                    forceblock.append(c)
            if board[b] == board[c] == None and board[a] == self.symbol:
                if c not in forks:
                    forceblock.append(b)
                if b not in forks:
                    forceblock.append(c)
        if len(forceblock) > 0:
            return random.choice(forceblock)
        return forks[0]

    def _moves_fork(self, board, symbol):
        """Return all moves that create a fork for the player specified by the symbol."""
        cells = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0}
        for row in Board._ROWS:
            a, b, c = row
            if board[a] == board[b] == None and board[c] == symbol:
                cells[a] += 1
                cells[b] += 1
            if board[a] == board[c] == None and board[b] == symbol:
                cells[a] += 1
                cells[c] += 1
            if board[b] == board[c] == None and board[a] == symbol:
                cells[b] += 1
                cells[c] += 1
        forks = [cell for cell, count in cells.items() if count > 1]
        return forks 

    def move_center (self, board):
        """Return the center cell if it is free."""
        if board[4] == None:
            return 4
        return None

    def move_opposite_corner(self, board):
        """Return a free corner opposite of the opponent."""
        corners = [[0, 8], [2, 6]]
        opponent_symbol = 'O'
        if self.symbol != 'X':
            opponent_symbol = 'X'
        for a, b in corners:
            if board[a] == opponent_symbol and board[b] == None:
                return b
            if board[a] == None and board[b] == opponent_symbol:
                return a
        return None

    def move_free_corner(self, board):
        """Return any free corner."""
        free_cells = board.get_free_cells()
        free_corners = [cell for cell in [0, 2, 6, 8] if cell in free_cells]
        if len(free_corners) > 0:
            return random.choice(free_corners)
        return None

    def move_random(self, board):
        """Return a random free cell."""
        free_cells = board.get_free_cells()
        if len(free_cells) > 0:
            return random.choice(free_cells)
        return None


class ConsolePlayer(Player):
    """A simple human player for the game Tic Tac Toe.

    The class interacts with a human player through the console.
    It displays the boards current state and asks the user to
    select a valid move.

    """
    def __init__(self, symbol, name="Player"):
        """Initialize the new player."""
        super(ConsolePlayer, self).__init__(symbol)
        self.name = name

    def __str__(self):
        """Return a nice string representation of the player."""
        return "{0} ({1})".format(self.name, self.symbol)

    def make_move(self, board):
        """Ask the user to make a valid move."""
        print()
        print(board)
        move = -1
        while not move in board.get_free_cells():
            print("{0}, your move (type 'q' to quit): ".format(self.name))
            playerinput = input()
            if move not in board.get_free_cells():
                print("Invalid move...")
            if playerinput.lower() == 'q':
                raise PlayerAbortException('Player has chosen to quit.')
            try:
                move = int(playerinput) - 1
            except ValueError:
                move = -1
        board[move] = self.symbol
        return move


class TicTacToe(object):
    """A game of Tic Tac Toe.

    This class implements the games basic rules. Two players take alternating
    turns placing their markers on the game board. This continues until either
    one of the players has won or there are no more free cells left.
    
    """
    def __init__(self, player1, player2):
        """Initialize a new game."""
        self.board = Board()
        self.players = [player1, player2]
        self.callbacks = []

    def reset(self):
        """Clear all cells on the game's board."""
        self.board = Board()

    def play(self):
        """Play a round of Tic Tac Toe.

        Let each player take turns until either one of the players wins
        the game or there are no more free cells on the board.
        Registered callback handlers will be called before the game starts,
        before each move, after each move and after the game ends.

        """
        b = self.board
        playercycle = itertools.cycle(self.players)
        for cb in self.callbacks:
            cb.pre_game_hook(self, self.board, self.players)
        while b.get_free_cells() != () and not b.winner():
            player = next(playercycle)
            for cb in self.callbacks:
                cb.pre_move_hook(self, self.board, self.players, player)
            move = player.make_move(b)
            for cb in self.callbacks:
                cb.post_move_hook(self, self.board, self.players, player, move)
            if b.get_free_cells() == () or b.winner():
                break
        for cb in self.callbacks:
            cb.post_game_hook(self, self.board, self.players, self.get_winner())

    def get_winner(self):
        """Return the winner of the current game."""
        winner = self.board.winner()
        for player in self.players:
            if winner == player.symbol:
                return player
        return None

    def register_callback(self, callback_handler):
        """Register a callback handler with the game instance."""
        self.callbacks.append(callback_handler)


class CallbackHandler(object, metaclass=ABCMeta):
    """An abstract callback handler for the game.
    
    This class can be subclassed to implement custom callback handlers
    for the game. A handler may supply up to four different methods that will
    be called at various points during the game.
    
    """
    
    def __init__(self):
        """Initialize the callback handler."""
        super(CallbackHandler, self).__init__()
        
    @abstractmethod
    def pre_game_hook(self, game, board, players):
        """This method is called before a game starts."""
        pass
        
    @abstractmethod
    def post_game_hook(self, game, board, players, winner):
        """This method is called once a game ends."""
        pass
        
    @abstractmethod
    def pre_move_hook(self, game, board, players, currentplayer):
        """This method is called before every move by any player."""
        pass
        
    @abstractmethod
    def post_move_hook(self, game, board, players, currentplayer, move):
        """This method is be called after every move."""
        pass


if __name__ == '__main__':
    def print_message(message):
        print()  
        print("*" * (len(message) + 4))
        print("* " + message + " *")
        print("*" * (len(message) + 4))
        print()

    class ResultDisplayHandler(CallbackHandler):
        """A callback handler that displays the boards state after a game ends."""
        def pre_game_hook(self, game, board, players):
            pass
            
        def post_game_hook(self, game, board, players, winner):
            if winner:
                if isinstance(winner, ConsolePlayer):
                    print_message("{0} wins!".format(winner.name))
                elif isinstance(winner, AiPlayer):
                    print_message("Computer ({0}) wins!".format(winner.symbol))
                else:
                    print_message("({0}) wins!".format(str(winner)))
            else:
                print_message("Draw!")
            print(board)
            print()
            
        def pre_move_hook(self, game, board, players, current):
            pass
        
        def post_move_hook(self, game, board, players, current, move):
            pass

    print_message("Welcome to Tic Tac Toe")
    while True:
        players = []
        for number, symbol in ([1, 'X'], [2, 'O']):
            player_type = None
            while not player_type in ['h', 'c']:
                player_type = input("Player {0} Human or Computer [h|c]? ".format(number)).lower()
            if player_type == 'h':
                name = "Player {0}".format(symbol)
                nameinput = input("Player name: ")
                if nameinput != "":
                    name = nameinput
                players.append(ConsolePlayer(symbol, name))
            else:
                while True:
                    try:
                        level = input("Difficulty: ")
                        players.append(AiPlayer(symbol, int(level)))
                        break
                    except ValueError:
                        pass
        new_game = 'r'
        while new_game == 'r':
            try:
                game = TicTacToe(*players)
                game.register_callback(ResultDisplayHandler())
                game.play()
            except PlayerAbortException as ex:
                pass
            question = [
                "Would you like to:",
                " r) Restart the last game",
                " n) Start a new game",
                " q) Quit"]
            print("\n".join(question))
            new_game = None            
            while new_game not in ('r', 'n', 'q'):
                new_game = input("? ").lower()
            if new_game == 'q' or new_game == 'n':
                break
        if new_game == 'q':
            break

