#!/bin/bash
command=$1; shift
slicename=$1; shift

# that can make sense if needed
# source /etc/init.d/functions

function start () {
    
}
function stop () {

}
function restart () {
  stop
  start
}
case $command in 
start) start ;;
stop) stop ;;
restart) restart ;;
*) echo "Unknown command in initscript $command for slice $slicename" ;;
esac
