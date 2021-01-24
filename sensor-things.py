#! /usr/bin/python3

import argparse
import functools
import logging
import os
import requests
import yaml

_INSTANCE = None
_LOGGER = logging.getLogger(os.path.splitext(os.path.basename(__file__))[0])

_DATASTREAM_RESOURCE = 'Datastreams'
_FEATURE_RESOURCE = 'FeaturesOfInterest'
_LOCATION_RESOURCE = 'Locations'
_OBSERVED_PROPERTY_RESOURCE = 'ObservedProperties'
_SENSOR_RESOURCE = 'Sensors'
_THING_RESOURCE = 'Things'

_YAML_KEY_TO_RESOURCE = {
    'datastreams': _DATASTREAM_RESOURCE,
    'features': _FEATURE_RESOURCE,
    'locations': _LOCATION_RESOURCE,
    'sensors': _SENSOR_RESOURCE,
    'observedProperties': _OBSERVED_PROPERTY_RESOURCE,
    'things': _THING_RESOURCE
}


_REFERENCE_KEY_TO_RESOURCE = {
    'Datastream': _DATASTREAM_RESOURCE,
    'Feature': _FEATURE_RESOURCE,
    'Location': _LOCATION_RESOURCE,
    'Sensor': _SENSOR_RESOURCE,
    'ObservedProperty': _OBSERVED_PROPERTY_RESOURCE,
    'Thing': _THING_RESOURCE
}


class ItemNotFoundException(RuntimeError):

    def __init__(self, resource, nameOrId):
        super().__init__('{id} of type {type} not found'.format(id=nameOrId,
                                                                type=resource))


class ItemsCreationDeferredException(RuntimeError):

    def __init__(self):
        super().__init__()
        self.deferred = {}

    def append(self, resource, item):
        if type(item) is ItemsCreationDeferredException:
            for k in item.deferred.keys():
                for v in item.deferred[k]:
                    self.append(k, v)
        else:
            deferred_for_type = self.deferred.get(resource, [])
            deferred_for_type.append(item)
            self.deferred[resource] = deferred_for_type

    def __bool__(self):
        return len(self.deferred) > 0


class SensorThingsAPI(object):

    def __init__(self, url, refresh=True):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.urls = self._getServerUrls(url)
        self.entities = {'Things': {},
                         'Datastreams': {},
                         'Locations': {},
                         'Sensors': {},
                         'ObservedProperties': {}
                         }
        self.logger.info('Connected to {url}.  {count} endpoints available.'.format(url=url,
                                                                                    count=(len(self.urls))))
        if refresh:
            self.refresh()

    def list(self, resource, count=10, offset=0):
        url = self.urls[resource]
        response = requests.get(url, {'$top': count, '$skip': offset})
        return response.json()['value']

    def search(self, resource, nameOrId):
        url = self.urls[resource]
        offset = 0
        count = 20
        while True:
            items = self.list(resource, count, offset)

            for i in items:
                if i['name'] == nameOrId or i['@iot.id'] == nameOrId:
                    return i

            if len(items) < count:
                raise ItemNotFoundException(resource, nameOrId)

            offset += count

    def create(self, resource, data, onlyIfNotExists=True):
        if onlyIfNotExists:
            nameOrId = data.get('@iot.id', data['name'])
            try:
                return self.search(resource, nameOrId)
            except ItemNotFoundException:
                pass

        try:
            url = self.urls.get(resource)
            response = requests.post(url, json=data)
            response.raise_for_status()

            obj = response.json()
            self.logger.info('Created new {type}: {id} ({name})'.format(type=resource.rstrip('s'),
                                                                        id=obj.get('@iot.id'),
                                                                        name=obj.get('name')))
            return obj
        except requests.exceptions.RequestException as ex:
            if hasattr(ex, 'response'):
                self.logger.error('Server response: ' +
                                  ex.response.json()['error']['message'][0])
            else:
                self.logger.exception(ex)

    def update(self, data):
        item_url = data.get('@iot.selfLink')
        if self.url not in item_url:
            self.logger.error('Own URL:  ' + self.url)
            self.logger.error('Item URL: ' + item_url)
            raise RuntimeError(
                'This item does not belong to this API instance')
        response = requests.put(item_url, data)
        response.raise_for_status()
        return response.json()

    def refresh(self):
        for k in self.entities.keys():
            entity_list = self.list(k, 100)
            self.logger.debug('Retrieved {count} {type}(s)'.format(count=len(entity_list),
                                                                   type=k))
            self.entities[k] = {}
            for e in entity_list:
                self.entities[k][e['@iot.id']] = e

    def _getServerUrls(self, base_url):
        base_url = base_url if base_url.endswith('v1.0') else '{url}/v1.0'.format(url=base_url)
        response = requests.get(base_url)
        response.raise_for_status()
        raw = response.json().get('value')
        return {item['name']: item['url'] for item in raw}


class _SensorThingsBase(object):

    def __init__(self, resource, data={}):
        self.resource = resource
        self.data = data
        self.logger = logging.getLogger(self.__class__.__name__)

    def create(self):
        remote_obj = _INSTANCE.create(self.resource, self.data)
        self.data.update(remote_obj)
        self.logger.info('Created new {type}: {id} ({name})'.format(type=self.__class__.__name__,
                                                                    id=self.data.get('@iot.id'),
                                                                    name=self.data.get('name')))


class Thing(_SensorThingsBase):

    def __init__(self, data={}):
        super().__init__('Things', data)


def _populate_references(item):
    for attr in ['Sensor', 'ObservedProperty', 'Thing']:
        value = item.get(attr)
        if value and type(value) is str:
            value = _INSTANCE.search(_REFERENCE_KEY_TO_RESOURCE[attr],
                                     value)
            item[attr] = value
    return item


def _process_yaml_element(el):
    deferred_elements = ItemsCreationDeferredException()
    if type(el) is dict:
        for k, value in el.items():
            resource = _YAML_KEY_TO_RESOURCE.get(k)
            if resource:
                _LOGGER.debug("Processing '{resource}'...".format(resource=resource))
                for v in value:
                    try:
                        v = _populate_references(v)
                        _INSTANCE.create(resource, v)
                    except ItemNotFoundException as ex:
                        _LOGGER.debug(str(ex))
                        _LOGGER.debug('Creation of {name} ({type}) deferred'.format(name=v['name'],
                                                                                    type=resource))
                        deferred_elements.append(k, v)
            else:
                _process_yaml_element(value)
    if deferred_elements:
        raise deferred_elements


def _cli_yaml(options):
    files_to_process = list(options.yaml)
    num_retries = 0

    while files_to_process and num_retries < 3:
        # NOTE: We make a copy of files_to_process so we can iterate on
        #       the copy and modify the original
        for yaml_file in list(files_to_process):
            _LOGGER.info('{action} YAML file: {file}'.format(action='Processing' if num_retries == 0 else 'Reprocessing',
                                                             file=yaml_file))

            try:
                with open(yaml_file) as stream:
                    data = yaml.safe_load(stream)
                    _process_yaml_element(data)

                # No exceptions, remove this file from the list to be processed
                files_to_process.remove(yaml_file)
            except ItemsCreationDeferredException:
                pass

        num_retries = num_retries + 1


def _cli(entity_type, options):
    _list_helper(entity_type, options)


def _list_helper(type_name, options):
    resource = _YAML_KEY_TO_RESOURCE[type_name]
    entity_list = _INSTANCE.list(resource,
                                 options.count if 'count' in options else 10,
                                 options.offset if 'offset' in options else 0)
    print('{count} {type}'.format(count=len(entity_list),
                                  type=resource))
    for e in entity_list:
        print('{id:>4}: {name}'.format(id=e['@iot.id'],
                                       name=e['name']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Interact with a SensorThings API instance')

    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument('-v', '--verbose', action='store_true')
    verbosity_group.add_argument('-s', '--silent', action='store_true')

    parser.add_argument('-d',
                        '--destination',
                        default='http://localhost:8080',
                        help='Specify the SensorThings destination URL')
    parser.add_argument('-r',
                        '--refresh',
                        action='store_true',
                        help='Upon startup, retrieve entities from the server')

    subparsers = parser.add_subparsers()

    # sensor-things yaml ...
    yaml_parser = subparsers.add_parser('yaml')
    yaml_parser.add_argument('yaml',
                             nargs='+',
                             metavar='YAML',
                             help='Create SensorThings data from the specified YAML file(s).  Implies --refresh')
    yaml_parser.set_defaults(func=_cli_yaml)

    common_list_options = argparse.ArgumentParser(add_help=False)
    common_list_options.add_argument('-c',
                                     '--count',
                                     default=10,
                                     help='Specify the maximum number of entities to retrieve')
    common_list_options.add_argument('-o',
                                     '--offset',
                                     default=0,
                                     help='Specify an offset for the items to retrieve')

    for entity_type in ['observedProperties', 'locations', 'features', 'sensors', 'datastreams', 'things']:
        # e.g.: sensor-things things ...
        things_parser = subparsers.add_parser(entity_type)
        things_parser.set_defaults(func=functools.partial(_cli, entity_type))
        things_subparser = things_parser.add_subparsers()

        # sensor-things things list ...
        things_list_parser = things_subparser.add_parser('list',
                                                         parents=[common_list_options])
        things_list_parser.set_defaults(func=functools.partial(_list_helper, entity_type))

    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.ERROR if args.silent else logging.INFO,
                        format='%(asctime)s [%(levelname)-5s] %(name)-20s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _INSTANCE = SensorThingsAPI(args.destination, args.refresh)

    args.func(args)
