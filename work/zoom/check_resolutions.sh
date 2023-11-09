#!/bin/bash
if ! command -v screenresolution &> /dev/null
then
    echo "screenresolution could not be found. Please run 'brew install screenresolution'"
    exit
fi
screenresolution get 2> /dev/null | grep -Eo '([0-9]+x[0-9]+)' > monitor_resolutions.conf
system_profiler SPDisplaysDataType | grep Resolution | sed -e 's/Resolution: //' > monitor_resolutions.conf