"""Main module of the blind chess game.

Only supports humans playing white at the moment.
"""

import sys
from enum import Enum

import chess
import stockfish

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

SPLASH_MESSAGE = r"""
 ____  __    __  __ _  ____     ___  _  _  ____  ____  ____
(  _ \(  )  (  )(  ( \(    \   / __)/ )( \(  __)/ ___)/ ___)
 ) _ (/ (_/\ )( /    / ) D (  ( (__ ) __ ( ) _) \___ \\___ \
(____/\____/(__)\_)__)(____/   \___)\_)(_/(____)(____/(____/
"""
START_POSITIONS = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class GameState(Enum):
    """Keeps track of the game state"""

    ONGOING = "ongoing"
    CHECKMATE = "checkmate"
    STALEMATE = "draw: stalemate"
    REPETITION = "draw: repetition"
    RESIGNED = "resigned"


class Analyzer:  # pylint: disable=too-few-public-methods
    """Stockfish analyzer for evaluation of positions"""

    def __init__(self) -> None:
        self.stockfish = stockfish.Stockfish("/opt/homebrew/bin/stockfish")
        self.stockfish.set_elo_rating(3500)

    def get_evaluation(self, fen_position: str) -> str:
        """Return the evaluation for the current position"""
        self.stockfish.set_fen_position(fen_position)
        evaluation = self.stockfish.get_evaluation()
        if evaluation["type"] == "cp":
            # centipawns:
            return evaluation["value"] / 100
        if evaluation["type"] == "mate":
            return f"mate {evaluation['value']}"
        return "? " + str(evaluation)


class Game:
    """Represent the game including objects and logic"""

    class CommandError(Exception):
        """Raise if there are any issues with the command input"""

    def __init__(self, start_pos: str = "") -> None:
        if start_pos:
            self.start_positions = start_pos
        else:
            self.start_positions = START_POSITIONS
        self.board = chess.Board(start_pos)
        self.stockfish = stockfish.Stockfish(
            "/opt/homebrew/bin/stockfish", parameters=STOCKFISH_SETTINGS
        )
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
        # Info
        if command.lower() in ["i", "info"]:
            if game.board.is_check():
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

    def do_human_move(self) -> str:
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

    def do_stockfish_move(self):
        """Let Stockfish do a move"""
        print(f"{len(str(self.move_counter)) * ' '}  Hmm....  ", end="", flush=True)
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
        print("My response:", response)
        self.board.push(opponent_move)
        self.update_game_state()

    def show_board(self):
        """Draw the board with ASCII characters"""
        self.stockfish.set_fen_position(self.board.fen())
        print(self.stockfish.get_board_visual())


if __name__ == "__main__":
    print(SPLASH_MESSAGE)

    if len(sys.argv) > 1:
        start_positions = sys.argv[1]
    else:
        start_positions = START_POSITIONS  # pylint: disable=invalid-name

    # Main loop:
    game = Game(start_pos=start_positions)
    print(game.get_welcome_message())
    print()
    while True:
        # Human player:
        game.do_human_move()
        print(game.game_state)
        if game.game_state is not GameState.ONGOING:
            print(f"\n*** {game.game_state.value.upper()}! ***\n")
            break
        if not game.opponents_turn:
            # Skip opponent's move
            continue

        game.do_stockfish_move()

        if game.game_state is not GameState.ONGOING:
            print(f"\n*** {game.game_state.value.upper()}! ***\n")
            break

        game.move_counter += 1

    # Print board:
    try:
        print(game.stockfish.get_board_visual())
    except stockfish.models.StockfishException as _exc:
        print(f"Could not draw the board due to a Stockfish error: {_exc}")
    print("----- FEN: -----")
    print(game.board.fen())
    # Print PGN:
    if start_positions.split(" ")[-1] == "1":
        print("----- PGN: -----")
        print(game.get_game_as_pgn())
    print("----------------")
