#!/bin/bash

function _control_ {
    for org in  arches              \
                death-valley        \
                denali              \
                dry-tortugas        \
                gates-of-the-arctic \
                glacier             \
                haleakala           \
                mammoth-cave        \
                mesaverde           \
                shenandoah          ;   do
        docker-compose  -f docker-compose.yml                       \
                        -f dev/docker-compose.override-${org}.yml   \
                        -p ${org}                                   \
                        $*
    done
}

case $1 in
    start)  _control_ up -d
            ;;
    stop)   _control_ rm --force --stop
            ;;
    *)      echo "Must be one of start|stop"
            ;;
esac
