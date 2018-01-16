"""
Module for playing games of Go using GoTextProtocol

This code is based off of the gtp module in the Deep-Go project
by Isaac Henrion and Amos Storkey at the University of Edinburgh.
"""
import traceback
import sys
import os
from board import GoBoard
from board_util import GoBoardUtil, BLACK, WHITE, EMPTY, BORDER, FLOODFILL
import numpy as np
import re
import time


class GtpConnection():

    def __init__(self, go_engine, debug_mode = False):
        """
        object that plays Go using GTP

        Parameters
        ----------
        go_engine: GoPlayer
            a program that is capable of playing go by reading GTP commands
        debug_mode: prints debug messages
        """
        self.stdout = sys.stdout
        sys.stdout = self
        self._debug_mode = debug_mode
        self.go_engine = go_engine
        self.komi = 0
        self.board = GoBoard(7)
        self.notdone = False
        self.timelimit = 1
        self.starttime = 0
        self.winMoves = []
        self.genCall = False
        self.commands = {
            "protocol_version": self.protocol_version_cmd,
            "quit": self.quit_cmd,
            "name": self.name_cmd,
            "boardsize": self.boardsize_cmd,
            "showboard": self.showboard_cmd,
            "clear_board": self.clear_board_cmd,
            "komi": self.komi_cmd,
            "version": self.version_cmd,
            "known_command": self.known_command_cmd,
            "set_free_handicap": self.set_free_handicap,
            "genmove": self.genmove_cmd,
            "list_commands": self.list_commands_cmd,
            "play": self.play_cmd,
            "final_score": self.final_score_cmd,
            "legal_moves": self.legal_moves_cmd,
            "timelimit": self.timelimit_cmd,
            "solve": self.solve_cmd
        }

        # used for argument checking
        # values: (required number or arguments, error message on argnum failure)
        self.argmap = {
            "boardsize": (1, 'Usage: boardsize INT'),
            "komi": (1, 'Usage: komi FLOAT'),
            "known_command": (1, 'Usage: known_command CMD_NAME'),
            "set_free_handicap": (1, 'Usage: set_free_handicap MOVE (e.g. A4)'),
            "genmove": (1, 'Usage: genmove {w, b}'),
            "play": (2, 'Usage: play {b, w} MOVE'),
            "legal_moves": (1, 'Usage: legal_moves {w, b}'),
            "timelimit": (1, 'Usage: timelimit seconds (1 <= seconds <= 100)')
        }
    
    def __del__(self):
        sys.stdout = self.stdout

    def write(self, data):
        self.stdout.write(data)

    def flush(self):
        self.stdout.flush()

    def start_connection(self):
        """
        start a GTP connection. This function is what continuously monitors
        the user's input of commands.
        """
        self.debug_msg("Start up successful...\n\n")
        line = sys.stdin.readline()
        while line:
            self.get_cmd(line)
            line = sys.stdin.readline()

    def get_cmd(self, command):
        """
        parse the command and execute it

        Arguments
        ---------
        command : str
            the raw command to parse/execute
        """
        if len(command.strip(' \r\t')) == 0:
            return
        if command[0] == '#':
            return
        # Strip leading numbers from regression tests
        if command[0].isdigit():
            command = re.sub("^\d+", "", command).lstrip()

        elements = command.split()
        if not elements:
            return
        command_name = elements[0]; args = elements[1:]
        
        if command_name == "play" and self.argmap[command_name][0] != len(args):
            self.respond('illegal move: {} wrong number of arguments'.format(args[0]))
            return

        if self.arg_error(command_name, len(args)):
            return
        if command_name in self.commands:
            try:
                self.commands[command_name](args)
            except Exception as e:
                self.debug_msg("Error executing command {}\n".format(str(e)))
                self.debug_msg("Stack Trace:\n{}\n".format(traceback.format_exc()))
                raise e
        else:
            self.debug_msg("Unknown command: {}\n".format(command_name))
            self.error('Unknown command')
            sys.stdout.flush()

    def arg_error(self, cmd, argnum):
        """
        checker funciton for the number of arguments given to a command

        Arguments
        ---------
        cmd : str
            the command name
        argnum : int
            number of parsed argument

        Returns
        -------
        True if there was an argument error
        False otherwise
        """
        if cmd in self.argmap and self.argmap[cmd][0] > argnum:
            self.error(self.argmap[cmd][1])
            return True
        return False

    def debug_msg(self, msg = ''):
        """ Write a msg to the debug stream """
        if self._debug_mode:
            sys.stderr.write(msg); sys.stderr.flush()

    def error(self, error_msg = ''):
        """ Send error msg to stdout and through the GTP connection. """
        sys.stdout.write('? {}\n\n'.format(error_msg)); sys.stdout.flush()

    def respond(self, response = ''):
        """ Send msg to stdout """
        sys.stdout.write('= {}\n\n'.format(response)); sys.stdout.flush()

    def reset(self, size):
        """
        Resets the state of the GTP to a starting board

        Arguments
        ---------
        size : int
            the boardsize to reinitialize the state to
        """
        self.board.reset(size)

    def protocol_version_cmd(self, args):
        """ Return the GTP protocol version being used (always 2) """
        self.respond('2')

    def quit_cmd(self, args):
        """ Quit game and exit the GTP interface """
        self.respond()
        exit()

    def name_cmd(self, args):
        """ Return the name of the player """
        self.respond(self.go_engine.name)

    def version_cmd(self, args):
        """ Return the version of the player """
        self.respond(self.go_engine.version)

    def clear_board_cmd(self, args):
        """ clear the board """
        self.reset(self.board.size)
        self.respond()

    def boardsize_cmd(self, args):
        """
        Reset the game and initialize with a new boardsize

        Arguments
        ---------
        args[0] : int
            size of reinitialized board
        """
        self.reset(int(args[0]))
        self.respond()

    def showboard_cmd(self, args):
        self.respond('\n' + str(self.board.get_twoD_board()))

    def komi_cmd(self, args):
        """
        Set the komi for the game

        Arguments
        ---------
        args[0] : float
            komi value
        """
        self.komi = float(args[0])
        self.respond()

    def known_command_cmd(self, args):
        """
        Check if a command is known to the GTP interface

        Arguments
        ---------
        args[0] : str
            the command name to check for
        """
        if args[0] in self.commands:
            self.respond("true")
        else:
            self.respond("false")

    def list_commands_cmd(self, args):
        """ list all supported GTP commands """
        self.respond(' '.join(list(self.commands.keys())))

    def set_free_handicap(self, args):
        """
        clear the board and set free handicap for the game

        Arguments
        ---------
        args[0] : str
            the move to handicap (e.g. B2)
        """
        self.board.reset(self.board.size)
        for point in args:
            move = GoBoardUtil.move_to_coord(point, self.board.size)
            point = self.board._coord_to_point(*move)
            if not self.board.move(point, BLACK):
                self.debug_msg("Illegal Move: {}\nBoard:\n{}\n".format(move, str(self.board.get_twoD_board())))
        self.respond()

    def legal_moves_cmd(self, args):
        """
        list legal moves for the given color
        Arguments
        ---------
        args[0] : {'b','w'}
            the color to play the move as
            it gets converted to  Black --> 1 White --> 2
            color : {0,1}
            board_color : {'b','w'}
        """
        try:
            board_color = args[0].lower()
            color = GoBoardUtil.color_to_int(board_color)
            moves = GoBoardUtil.generate_legal_moves(self.board, color)
            self.respond(moves)
        except Exception as e:
            self.respond('Error: {}'.format(str(e)))

    def play_cmd(self, args):
        """
        play a move as the given color

        Arguments
        ---------
        args[0] : {'b','w'}
            the color to play the move as
            it gets converted to  Black --> 1 White --> 2
            color : {0,1}
            board_color : {'b','w'}
        args[1] : str
            the move to play (e.g. A5)
        """
        try:
            board_color = args[0].lower()
            board_move = args[1]
            color = GoBoardUtil.color_to_int(board_color)
            move = GoBoardUtil.move_to_coord(args[1], self.board.size)
            if move:
                move = self.board._coord_to_point(move[0], move[1])
            else:
                return
            if not self.board.move(move, color):
                return
            self.respond()
        except Exception as e:
            self.respond("illegal move: {} {} {}".format(board_color, board_move, str(e)))

    def final_score_cmd(self, args):
        self.respond(self.board.final_score(self.komi))

    def genmove_cmd(self, args):
        """
        generate a move for the specified color

        Arguments
        ---------
        args[0] : {'b','w'}
            the color to generate a move for
            it gets converted to  Black --> 1 White --> 2
            color : {0,1}
            board_color : {'b','w'}
        """
        try:
            self.notdone = False
            board_color = args[0].lower()
            color = GoBoardUtil.color_to_int(board_color)
            #TODO
            if self.board.get_winner() != None:
                self.respond("resign")
                return
            self.winMoves = []
            self.genCall = True
            if args[0] != None:
                if args[0] == 'b':
                    self.board.to_play = BLACK
                else:
                    self.board.to_play = WHITE
            self.solve_cmd(args)

            self.genCall = False

            if len(self.winMoves) != 0:
                row, col = GoBoardUtil.move_to_coord(self.winMoves[0], self.board.size)
                move = self.board._coord_to_point(row, col)
                #self.respond(self.winMoves[0])

            else:
                move = GoBoardUtil.generate_random_move(self.board, color)
                move = self.board._point_to_coord(move)
                move = GoBoardUtil.format_point(move)
                row, col = GoBoardUtil.move_to_coord(move, self.board.size)
                move = self.board._coord_to_point(row, col)
                #self.respond(move)

            if not self.board.check_legal(move, color):
                move = self.board._point_to_coord(move)
                board_move = GoBoardUtil.format_point(move)
                self.respond("Illegal move: {}".format(board_move))
                raise RuntimeError("Illegal move given by engine")

            # move is legal; play it

            self.board.move(move, color)
            self.debug_msg("Move: {}\nBoard: \n{}\n".format(move, str(self.board.get_twoD_board())))
            move = self.board._point_to_coord(move)
            board_move = GoBoardUtil.format_point(move)
            self.respond(board_move)
        except Exception as e:
            self.respond('Error: {}'.format(str(e)))


    def timelimit_cmd(self, args):
        #TODO
        self.timelimit = int(args[0])
        self.respond()  

    def solve_cmd(self, args):
        #TODO
        self.winMoves = []
        self.notdone = False
        state = self.board
        self.starttime = time.process_time()
        #win = self.negamaxBoolean(state,0)
        win = self.alphabeta(state, -100000, 100000, 0)
        stone = ['', 'b', 'w']
        
        i = 1
        if not self.genCall: 
            
            if len(self.winMoves) != 0:
                s = stone [state.to_play]
                self.respond("{} {}".format(s, self.winMoves[0]))
            else:
                if self.notdone:
                    self.respond("unknown")
                else:
                    s = stone [GoBoardUtil.opponent(state.to_play)]
                    self.respond(s)
    # helper function for solve
    # Success means: either a win, or toPlay is the DRAW_WINNER when its a draw

    def negamaxBoolean(self, state, depth):
        result = False
        duration = time.process_time() - self.starttime

        #if duration > self.timelimit:
            #self.notdone = True
            #print("[Unknown]\n")
            #return 
        
        if state.get_winner() != None:
            return ( state.get_winner() == state.to_play)

        for m in (GoBoardUtil.generate_legal_moves(state, state.to_play).split(' ')):
            point = GoBoardUtil.move_to_coord(m, state.size)
            point = state._coord_to_point(point[0], point[1])

            state.move(point,state.to_play)

            success = not self.negamaxBoolean(state,depth + 1)

            state.board[point] = EMPTY
            state.to_play = GoBoardUtil.opponent(state.to_play)

            if success:
                if depth == 0:
                    self.winMoves.append(m)
                result = True
            #if self.notdone: 
                #return result
        return result

    def alphabeta(self, state, alpha, beta, d):
        
        duration = time.process_time() - self.starttime
        
        if self.notdone or self.winMoves != []: 
            return 'a'            

        if duration > self.timelimit:
            self.notdone = True
            #print("[Unknown]\n")
            return 'a'
        
        if state.get_winner() != None:
            return state.staticallyEvaluateForToPlay() 
        
        for m in (GoBoardUtil.generate_legal_moves(state, state.to_play).split(' ')):
            point = GoBoardUtil.move_to_coord(m, state.size)
            point = state._coord_to_point(point[0], point[1])
            
            state.move(point,state.to_play)
            try:
                value = -int(self.alphabeta(state, -beta, -alpha, d+1))
            except:
                state.board[point] = EMPTY
                state.to_play = GoBoardUtil.opponent(state.to_play)                   
                return 'a'
            
            state.board[point] = EMPTY
            state.to_play = GoBoardUtil.opponent(state.to_play)   
            
            if value > alpha:
                alpha = value
                if d == 0 and value >= 0:
                    self.winMoves.append(m)
                    return 'a'
                           
                
            if self.notdone or self.winMoves != []: 
                return 'a'
            
            if value >= beta: 
                return beta   # or value in failsoft (later)
        return alpha    