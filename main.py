"""Main module of the blind chess game."""

import os
import random
import sys
from enum import Enum

import chess
import stockfish


STOCKFISH_PATH = os.environ.get("STOCKFISH_PATH", "/opt/homebrew/bin/stockfish")
STOCKFISH_SETTINGS = {
    "Debug Log File": "",
    "Contempt": 0,
    "Min Split Depth": 0,
    "Threads": 4,
    "Ponder": "true",  # "false",
    "Hash": 16,
    "MultiPV": 1,
    "Skill Level": 1,
    "Move Overhead": 10,
    "Minimum Thinking Time": 2,
    "Slow Mover": 100,
    "UCI_Chess960": "false",
    "UCI_LimitStrength": "true",  # "false",
    "UCI_Elo": 1350,
}
START_POSITION = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
SPLASH_MESSAGE = r"""
 ____  __    __  __ _  ____     ___  _  _  ____  ____  ____
(  _ \(  )  (  )(  ( \(    \   / __)/ )( \(  __)/ ___)/ ___)
 ) _ (/ (_/\ )( /    / ) D (  ( (__ ) __ ( ) _) \___ \\___ \
(____/\____/(__)\_)__)(____/   \___)\_)(_/(____)(____/(____/
"""
HELP_MESSAGE = """
At the input prompt, enter your move as SAN (e.g. e4, exd5, Bc2 etc)
or one of the commands specified below

Commands:

    h or help   - show this information
    b or board  - show the current board
    i or info   - show information about the current position
    q or quit   - leave the game
    exit        - same as quit

"""


class GameState(Enum):
    """Keeps track of the game state"""

    ONGOING = "ongoing"
    CHECKMATE = "checkmate"
    STALEMATE = "draw: stalemate"
    REPETITION = "draw: repetition"
    RESIGNED = "resigned"


class StockfishMod(stockfish.Stockfish):
    """Modified Stockfish class, make the destructor more robust"""

    def __del__(self):
        """Catch attribute errors thrown during cleanup"""
        try:
            super().__del__()
        except AttributeError:
            pass

class Analyzer:  # pylint: disable=too-few-public-methods
    """Stockfish analyzer for evaluation of positions"""

    class StockfishError(Exception):
        """Raise when there are issues with Stockfish"""

    def __init__(self) -> None:
        try:
            self.stockfish = StockfishMod(STOCKFISH_PATH)
        except (AttributeError, FileNotFoundError):
            print("Could not find Stockfish. Exiting...")
            sys.exit(1)
        self.stockfish.set_elo_rating(3500)

    def get_evaluation(self, fen_position: str) -> str:
        """Return the evaluation for the current position"""
        self.stockfish.set_fen_position(fen_position)
        evaluation = self.stockfish.get_evaluation()
        if evaluation["type"] == "cp":
            # centipawns:
            return evaluation["value"] / 100
        if evaluation["type"] == "mate":
            return f"""mate {evaluation["value"]}"""
        return "? " + str(evaluation)


class Game:
    """Represent the game including objects and logic"""

    class CommandError(Exception):
        """Raise if there are any issues with the command input"""

    def __init__(self, *, start_pos: str = "") -> None:
        if start_pos:
            self.start_positions = start_pos
        else:
            self.start_positions = START_POSITION
        self.board = chess.Board(start_pos)
        self.stockfish = StockfishMod(STOCKFISH_PATH, parameters=STOCKFISH_SETTINGS)
        self.analyzer = Analyzer()
        self.stockfish.set_fen_position(self.board.fen())
        self.move_counter = int(start_pos.split(" ")[-1])
        self.game_state: GameState = GameState.ONGOING
        self.latest_command: str = ""
        self.opponents_turn: bool = False

    def get_game_as_pgn(self) -> str:
        """Create a PGN string from the current game"""
        temp_board = chess.Board(self.start_positions)
        move_count = 1
        out = ""
        for move_no, move in enumerate(self.board.move_stack, start=1):
            if move_no % 2:
                out += f"{move_count}. "
                move_count += 1
            out += temp_board.san(move) + " "
            temp_board.push(move)
        return out

    def get_welcome_message(self) -> str:
        """Return Stockfish version and settings"""
        return (
            "Opponent: Stockfish "
            f"{self.stockfish.get_stockfish_major_version()}"
            f' with elo {self.stockfish.get_parameters()["UCI_Elo"]}'
        )

    def update_game_state(self) -> str:
        """Check game state and update the class variable"""
        if self.board.is_checkmate():
            self.game_state = GameState.CHECKMATE
        elif self.board.is_stalemate():
            self.game_state = GameState.STALEMATE
        elif self.board.is_repetition():
            self.game_state = GameState.REPETITION
        else:
            self.game_state = GameState.ONGOING

    def do_command(self, command: str) -> bool:
        """Execute a user command. Returns False if it was a move, True otherwise"""
        # Help
        if command.lower() in ["h", "help"]:
            print(HELP_MESSAGE)
            return True

        # Info
        if command.lower() in ["i", "info"]:
            if self.board.is_check():
                print("     In check!")
            print(
                "     Allowed to castle:",
                "yes" if self.board.has_castling_rights(chess.WHITE) else "no",
            )
            print("     Evaluation:", self.analyzer.get_evaluation(self.board.fen()))
            return True

        # Show?
        if command.lower() in ["b", "board"]:
            self.show_board()
            return True

        # Quit?
        if command.lower() in ["q", "quit", "exit"]:
            self.game_state = GameState.RESIGNED
            return True

        return False

    def do_human_move(self) -> bool:
        """Get input from the human player"""
        try:
            command = input(f"{self.move_counter}. Your move or command: ")
        except KeyboardInterrupt:
            self.game_state = GameState.RESIGNED
            return

        self.opponents_turn = False
        try:
            human_move = self.board.parse_san(command)
            self.board.push(human_move)
            self.opponents_turn = True
        except (chess.IllegalMoveError, chess.InvalidMoveError) as exc:
            result = self.do_command(command)
            if not result:
                print(f"😨 {self.CommandError(exc)}")
        if not self.game_state == GameState.RESIGNED:
            self.update_game_state()
        
        return self.opponents_turn

    def do_stockfish_move(self) -> bool:
        """Let Stockfish do a move"""
        print(f"{self.move_counter}. Hmm....  ", end="", flush=True)
        self.stockfish.set_fen_position(self.board.fen())
        ai_move_uci = self.stockfish.get_best_move()
        # ai_move_uci = STOCKFISH.get_top_moves(5)[-1]
        ai_move = self.board.parse_uci(ai_move_uci)
        try:
            response = (
                self.stockfish.get_what_is_on_square(ai_move_uci[:-2]).value.upper(),
                ai_move,
            )
        except ValueError:
            response = "? " + ai_move_uci
        opponent_move = ai_move

        response = self.board.san(opponent_move)
        print("    My move:", response)
        self.board.push(opponent_move)
        self.update_game_state()
        self.opponents_turn = True

        return True

    def show_board(self):
        """Draw the board with ASCII characters"""
        self.stockfish.set_fen_position(self.board.fen())
        print(self.stockfish.get_board_visual())


def main(*, start_positions=None):
    """Game controller"""
    ################
    # PREPARE GAME
    #
    print("Would you prefer to play as white, black or random?")
    side = input("Enter b, w or r: ")
    print()
    print("What elo rating would you prefer Stockfish to have?")
    elo = input("Enter the elo number or press enter for default (1350): ")
    print()
    if elo:
        STOCKFISH_SETTINGS["UCI_Elo"] = elo

    if not start_positions:
        start_positions = START_POSITION

    # Create the game:
    game = Game(start_pos=start_positions)
    welcome_message = game.get_welcome_message()
    print("-" * (len(welcome_message) + 4))
    print("  " + welcome_message)
    print("-" * (len(welcome_message) + 4))

    print(HELP_MESSAGE)

    #############
    # MAIN LOOP
    #

    if side.lower() in ("r", "random"):
        side = random.choice(("black", "white"))

    if side.lower() in ("b", "black"):
        print("You play black!")
        order = (game.do_stockfish_move, game.do_human_move)
    elif side.lower() in ("w", "white"):
        print("You play white!")
        order = (game.do_human_move, game.do_stockfish_move)
    else:
        print(f"Illegal side, has to be one of r, b, or w! You entered {side}")
        sys.exit(1)

    game.opponents_turn = True
    should_continue = True
    while should_continue:
        first_move, second_move = order

        for move in (first_move, second_move):
            if not game.opponents_turn:
                # Skip opponent's move
                continue
            
            is_move = False
            while not is_move:
                is_move = move()
                if game.game_state is not GameState.ONGOING:
                    print(f"\n*** {game.game_state.value.upper()}! ***\n")
                    should_continue = False
                    break

        game.move_counter += 1

    ###############
    # END OF GAME
    #
    # Print board:
    try:
        print(game.stockfish.get_board_visual())
    except stockfish.models.StockfishException as _exc:
        print(f"Could not draw the board due to a Stockfish error: {_exc}")
    # Print FEN:
    print("----- FEN: -----")
    print(game.board.fen())
    # Print PGN:
    if start_positions.split(" ")[-1] == "1":
        print("----- PGN: -----")
        print(game.get_game_as_pgn())
    print("----------------")


if __name__ == "__main__":
    print(SPLASH_MESSAGE)

    POS = None
    if len(sys.argv) > 1:
        POS = sys.argv[1]

    main(start_positions=POS)
