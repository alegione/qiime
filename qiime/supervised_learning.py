#!/usr/bin/env python

__author__ = "Dan Knights"
__copyright__ = "Copyright 2011, The QIIME Project"
__credits__ = ["Dan Knights"]
__license__ = "GPL"
__version__ = "1.5.0-dev"
__maintainer__ = "Dan Knights"
__email__ = "daniel.knights@colorado.edu"
__status__ = "Development"

from os import remove, path, devnull
from os.path import join, split, splitext, exists
from numpy import array, set_printoptions, nan
from cogent.app.util import CommandLineApplication, CommandLineAppResult, \
    FilePath, ResultPath, ApplicationError
from qiime.util import get_qiime_project_dir
from cogent.app.parameters import Parameters
from biom.parse import convert_biom_to_table
from cogent.app.parameters import ValuedParameter, FlagParameter, FilePath

def parse_feature_importances(filepath):
    """Returns vector of feature IDs, vector of importance scores
    """
    lines = open(filepath,'U').readlines()
    feature_IDs = []
    scores = []
    for line in lines[1:]:
        words = line.strip().split('\t')
        feature_IDs.append(words[0].strip())
        scores.append(float(words[1].strip()))
    return array(feature_IDs), array(scores)

def run_supervised_learning(predictor_fp, response_fp, response_name, 
        ntree=1000, errortype='oob', output_dir='.', verbose=False, HALT_EXEC=False):
    # instantiate the object
    rsl = RSupervisedLearner(HALT_EXEC=HALT_EXEC)

    # set options
    rsl.Parameters['-m'].on(response_fp)
    rsl.Parameters['-c'].on(response_name)
    rsl.Parameters['-n'].on(str(ntree))
    rsl.Parameters['-o'].on(output_dir)
    rsl.Parameters['-e'].on(errortype)

    if verbose:
        rsl.Parameters['-v'].on()

    app_result = rsl(predictor_fp)

    ### Hack: delete the temporary otu table left behind by hack biom conversion
    remove(join(output_dir, splitext(split(predictor_fp)[1])[0] + '.txt'))

    return app_result
    
    
class RSupervisedLearner(CommandLineApplication):
    """ ApplicationController for detrending ordination coordinates
    """

    _command = 'R'
    _r_script = 'randomforests.r'
    
    _parameters = {\
         #input data table, e.g. otu table
         '-i':ValuedParameter(Prefix='-',Name='i',Delimiter=' ',IsPath=True),\
         # metadata table filepath
         '-m':ValuedParameter(Prefix='-',Name='m',Delimiter=' ',IsPath=True),\
         # metadata category header
         '-c':ValuedParameter(Prefix='-',Name='c',Delimiter=' '),\
         # error type = 'oob', 'cv5', 'cv10', 'loo'
         '-e':ValuedParameter(Prefix='-',Name='e',Delimiter=' '),\
         '-n':ValuedParameter(Prefix='-',Name='n',Delimiter=' '),\
         # output dir
         '-o':ValuedParameter(Prefix='-',Name='o',Delimiter=' ',IsPath=True),\
         '-v':FlagParameter(Prefix='-',Name='v'),\
     }
    _input_handler = '_input_as_parameter'
    _suppress_stdout = False
    _suppress_stderr = False

    def _input_as_parameter(self,data):
        """ Set the input path and log path based on data (a fasta filepath)
        """
        ## temporary hack: this converts a biom file to classic otu table
        ##  format for use within R
        if self.Parameters['-v'].Value:
            print 'Converting BIOM format to tab-delimited...'
        temp_predictor_fp = join(self.Parameters['-o'].Value,
                                 splitext(split(data)[1])[0]+'.txt')
        temp_predictor_f = open(temp_predictor_fp,'w')
        temp_predictor_f.write(convert_biom_to_table(open(data,'U')))
        temp_predictor_f.close()
        predictor_fp = temp_predictor_fp
        
        self.Parameters['-i'].on(predictor_fp)
        # access data through self.Parameters so we know it's been cast
        # to a FilePath
        return ''

    def _get_result_paths(self,data):
        """ Build the dict of result filepaths
        """
        # access data through self.Parameters so we know it's been cast
        # to a FilePath
        wd = self.WorkingDir
        od = self.Parameters['-o'].Value
        result = {}
        result['confusion_matrix'] = ResultPath(Path=join(od,'confusion_matrix.txt'), IsWritten=True)
        result['cv_probabilities'] = ResultPath(Path=join(od,'cv_probabilities.txt'), IsWritten=True)
        result['features'] = ResultPath(Path=join(od,'feature_importance_scores.txt'), IsWritten=True)
        result['mislabeling'] = ResultPath(Path=join(od,'mislabeling.txt'), IsWritten=True)
        result['summary'] = ResultPath(Path=join(od, 'summary.txt'), IsWritten=True)
        return result

    def _get_R_script_dir(self):
        """Returns the path to the qiime R source directory
        """
        qiime_dir = get_qiime_project_dir()
        script_dir = join(qiime_dir,'qiime','support_files','R')
        return script_dir

    def _get_R_script_path(self):
        """Returns the path to the R script to be executed
        """
        return join(self._get_R_script_dir(), self._r_script)

    # Overridden to add R-specific command-line arguments
    # This means:
    # R --slave --vanilla --args --source_dir $QIIMEDIR/qiime/support/R/ <normal params> < detrend.r
    def _get_base_command(self):
        """Returns the base command plus command-line options.

        Does not include input file, output file, and training set.
        """
        cd_command = ''.join(['cd ', str(self.WorkingDir), ';'])
        r_command = self._commandline_join(['R','--slave','--vanilla','--args'])
        source_dir_arg = self._commandline_join(['--source_dir',
                                                        self._get_R_script_dir()])

        script_arguments = self._commandline_join(
            [self.Parameters[k] for k in self._parameters])

        command_parts = [
            cd_command, r_command, source_dir_arg,
            script_arguments, '<', self._get_R_script_path()]
        return self._commandline_join(command_parts).strip()
    
    BaseCommand = property(_get_base_command)

    def _commandline_join(self, tokens):
        """Formats a list of tokens as a shell command
 
        This seems to be a repeated pattern; may be useful in
        superclass.
        """
        commands = filter(None, map(str, tokens))
        return self._command_delimiter.join(commands).strip()

    def _accept_exit_status(self,exit_status):
        """ Return True when the exit status was 0
        """
        return exit_status == 0
