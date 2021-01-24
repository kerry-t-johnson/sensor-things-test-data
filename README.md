# regis-msse692-sensor-things

## Test Server(s) and Test Data

### Running the test server(s)

> Requires Docker and Docker Compose

```bash
# Launches the Mesa Verde (fake organization) server at port 18080
$ docker-compose -f docker-compose.yml                          \
                 -f dev/docker-compose.override-mesaverde.yml   \
                 -p mesaverde                                   \
                 up [-d]

# Idempotently loads the Mesa Verde test data to the Mesa Verde
# server at port 18080:
$ ./sensor-things.py -v                         \
                     -d http://localhost:18080  \
                     yaml                       \
                     ./dev/common-data.yml      \
                     ./dev/mesaverde-data.yml

# Launches the Shenandoah (fake organization) server at port 28080
$ docker-compose -f docker-compose.yml                          \
                 -f dev/docker-compose.override-shenandoah.yml  \
                 -p shenandoah                                  \
                 up [-d]

# Idempotently loads the Shenandoah test data to the Shenandoah
# server at port 28080:
$ ./sensor-things.py -v                         \
                     -d http://localhost:28080  \
                     yaml                       \
                     ./dev/common-data.yml      \
                     ./dev/shenandoah-data.yml
```

### Stopping the test server(s)

```bash
# Stops the Mesa Verde server
$ docker-compose -f docker-compose.yml                          \
                 -f dev/docker-compose.override-mesaverde.yml   \
                 -p mesaverde                                   \
                 rm --stop --force

# Stops the Shenandoah server
$ docker-compose -f docker-compose.yml                          \
                 -f dev/docker-compose.override-shenandoah.yml  \
                 -p shenandoah                                  \
                 rm --stop --force

```

### Removing the test data

> NOTE: This step is not normally necessary

```bash
# The data is stored in local Docker volumes:
$ docker volume ls
local     mesaverde_gost_conf
local     mesaverde_mosquitto_data
local     mesaverde_nodered
local     mesaverde_postgis
local     shenandoah_gost_conf
local     shenandoah_mosquitto_data
local     shenandoah_nodered
local     shenandoah_postgis

# Remove individual volumes (containers must be stopped first)
$ docker volume rm [volume] [volume...]

# Remove all unused volumes (containers must be stopped first)
# NOTE: This command is not limited to test data!
$ docker volume container prune [-f]
```
