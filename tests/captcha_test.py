import sys,os
sys.path.insert(1, os.path.join(sys.path[0], '..'))

import time
from gui.captcha import  show_captcha
time.sleep(3)
a=show_captcha(os.path.abspath("../pass_code.jpeg"))
print a
