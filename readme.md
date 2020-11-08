# HBLoader

Intended to install software from Eclipse HawkBit server.


## Prerequisites

Hardware: Raspberry PI
OS: Raspbian


## Configure
hboader

1. git pull https://github.com/Janiot/hbloader.git
1. cd hbloader
1. rename hblcfg_sample.json to hblcfg.json 
1. sudo nano hblcfg.json
2. Enter tenant_id, login and password
3. sudo pip3 install -r requirements.txt
4. sudo python3 hbloader.py
5. go to https://console.eu1.bosch-iot-rollouts.com/UI/#!deployment and deploy APP

1. sudo docker ps 
2. sudo docker stop xy
3. sudo docker rm xy



License: LGPLv2.1

Copyright
---------

    Copyright (C) Additional code Eugene Nuribekov & Jan Alsters

Software based on rauc-hawkbit
https://github.com/rauc/rauc-hawkbit

    Copyright (C) 2016-2020 Pengutronix, Enrico Joerns <entwicklung@pengutronix.de>
    Copyright (C) 2016-2020 Pengutronix, Bastian Stender <entwicklung@pengutronix.de>
    
    This library is free software; you can redistribute it and/or
    modify it under the terms of the GNU Lesser General Public
    License as published by the Free Software Foundation; either
    version 2.1 of the License, or (at your option) any later version.
    
    This library is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
    Lesser General Public License for more details.
    
    You should have received a copy of the GNU Lesser General Public
    License along with this library; if not, write to the Free Software
    Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA



