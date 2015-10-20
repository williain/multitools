from __future__ import print_function
import sys
import os
import os.path
MODULE='multitools'

installs=[entry for entry in sys.path if os.path.exists(os.path.join(entry, 'multitools'))]
if len(installs)==0:
    print("Module hasn't been installed; Run setup.py install first")
    exit(1)
install=os.path.join(installs[0],MODULE)

def diff(localpath,installpath):
    for fil in os.listdir(localpath):
        localfil=os.path.join(localpath, fil)
        if os.path.isdir(localfil):
            if not diff(localfil, os.path.join(installpath,fil)):
                return False
        elif fil.endswith('.py'):
            installfil=os.path.join(installpath,fil)
            if not os.path.exists(installfil):
                return False
            elif os.path.getsize(localfil) != os.path.getsize(installfil):
                return False
            else:
                lfil=open(localfil)
                ifil=open(installfil)
                for line in lfil:
                    if line != ifil.readline():
                        lfil.close()
                        ifil.close()
                        return False
    return True

if not diff('src',install):
    print("Module installed is at a different version to local module;")
    print("Run setup.py install again")
    exit(1)
else:
    exit(0)

