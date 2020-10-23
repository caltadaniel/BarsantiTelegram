This is the barsanti control centre.
To automatically run the python script at the startup add the following lines in /etc/rc.local:
sleep 10
cd /home/pi/ShellScript
sudo -H -u pi ./launcher.sh

Then create a bash script called launcher.sh in /home/pi/ShellScript and add the following lines:

#!/bin/sh
#launcher.sh

cd /
cd home/pi/Git/BarsantiTelegram
python3 barsanti_telegram.py -t PUTTHEPROVIDEDKEY &

and then make it executable with chmod 755 launcher.sh

The program now must be correctly set-up to run at every startup

# new update
added systemctl service
copy barstel.service in /etc/systemd/system
start the service: sudo systemctl start barstel.service
enable it to run at the startup: sudo systemctl enable barstel.service
reboot the machine


