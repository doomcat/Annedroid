'''
@author: Owain Jones [odj@aber.ac.uk]
'''

from time import time

class Logger:
    '''
    Singleton class, for logging stuff to file.  
    '''

    class __impl:
        file = None

        def log(self, message):
            if self.file is None:
                print "["+str(time())+"]: "+message
                
        l = log

    __instance = None

    def __init__(self):
        '''
        Return the logger singleton, create it if it doesn't exist yet  
        '''
        if Logger.__instance is None:
            Logger.__instance = Logger.__impl()
            
        self.__dict__['_Logger__instance'] = Logger.__instance
        
    def __getattr__(self, attr):
        return getattr(self.__instance, attr)
    
    def __setattr__(self, attr):
        return setattr(self.__instance, attr)
