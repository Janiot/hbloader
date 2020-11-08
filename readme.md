# HBLoader

Intended to install software from Eclipse HawkBit server.


## Prerequisites

Hardware: Raspberry PI
OS: Raspbian


## Configure
hboader

    git pull https://github.com/Janiot/hbloader.git
    cd hbloader
    rename hblcfg_sample.json to hblcfg.json 
    sudo nano hblcfg.json
    Enter tenant_id, login and password
    sudo pip3 install -r requirements.txt
    sudo python3 hbloader.py
    go to https://console.eu1.bosch-iot-rollouts.com/UI/#!deployment and deploy APP

### Stop & remove Docker Container

    sudo docker ps 
    sudo docker stop xy
    sudo docker rm xy



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



