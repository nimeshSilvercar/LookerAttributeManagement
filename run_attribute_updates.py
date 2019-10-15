import calendar
from collections import defaultdict
from datetime import datetime
from itertools import groupby
import logging
import os
import lookerapi
import yaml

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

METADATA_LOOK_ID = 6
DEV_HOST_NAME = 'devdealerware'
PROD_HOST_NAME = 'insights'
ENVIRONMENTS = ('dev', 'prod')
SPECIAL_CASE_ATTRIBUTES = ('first_of_month', 'last_of_month')
EXCLUDED_ATTRIBUTES = ('locale', 'number_format')


def lambda_handler(event=None, context=None):
    """"Driver handling function, execute main function in each environment."""
    now = datetime.now()
    logger.info('Function beginning execution at time: {}'.format(now))

    # Authenticate to Dev instance, which is assumed always necessary to pull Dealer Group metadata table.
    if event is None and context is None:
        # Pull credentials from YAML file in same folder if running locally.
        with open('config.yml', 'r') as config_file:
            params = yaml.load(config_file, Loader=yaml.FullLoader)
            base_url_dev = params['hosts'][DEV_HOST_NAME]['host']
            client_id_dev = params['hosts'][DEV_HOST_NAME]['token']
            client_secret_dev = params['hosts'][DEV_HOST_NAME]['secret']
            base_url_prod = params['hosts'][PROD_HOST_NAME]['host']
            client_id_prod = params['hosts'][PROD_HOST_NAME]['token']
            client_secret_prod = params['hosts'][PROD_HOST_NAME]['secret']
    else:
        base_url_dev = os.environ['host_name']
        client_id_dev = os.environ['token']
        client_secret_dev = os.environ['secret']
        base_url_prod = os.environ['host_name_prod']
        client_id_prod = os.environ['token_prod']
        client_secret_prod = os.environ['secret_prod']

    client_dev = authenticate_to_looker(base_url_dev, client_id_dev, client_secret_dev)
    client_prod = authenticate_to_looker(base_url_prod, client_id_prod, client_secret_prod)

    # Get metadata table.
    oem_metadata_table = get_metadata_table(client_dev, METADATA_LOOK_ID)

    # Execute metadata Looker API updates to each instance.
    for environment in ENVIRONMENTS:
        if environment == 'dev':
            run_oem_group_attribute_updates(oem_metadata_table, environment, client_dev)
        else:
            run_oem_group_attribute_updates(oem_metadata_table, environment, client_prod)


def run_oem_group_attribute_updates(metadata_table, environment, client):
    """Run updates to Looker Groups, User Attributes and assigned Group Attributes based on metadata table.

    :param metadata_table: List of dictionaries representing the input metadata table.
    :param environment: String representing the environment we are running in, either 'prod' or 'dev'.
    :param client: API client for Looker instance.
    :return: None.
    """
    if environment.lower() == 'prod':
        url_field = 'dealerware_oem_metadata_url_prod'
    else:
        url_field = 'dealerware_oem_metadata_url_dev'

    group_api = lookerapi.GroupApi(client)
    user_attribute_api = lookerapi.UserAttributeApi(client)

    # First, pull existing Looker components.
    group_id_names = {}
    all_groups = group_api.all_groups(fields='id,name')
    for group in all_groups:
        group_id_names[group.name] = group.id

    attribute_id_details = {}
    all_attributes = user_attribute_api.all_user_attributes()
    for attribute in all_attributes:
        if not attribute.is_system and attribute.name not in EXCLUDED_ATTRIBUTES:
            attribute_id_details[attribute.name] = [attribute.id, attribute.type, attribute.default_value]

    metadata_group_attributes = metadata_table

    # Handle for any missing Looker components by adding them.
    meta_attributes = []
    meta_groups = []
    for mapping in metadata_group_attributes:
        if len(mapping[url_field]) > 0:
            meta_attributes.append([mapping['dealerware_oem_metadata_user_attribute_name'],
                                    mapping['dealerware_oem_metadata_user_attribute_type'],
                                    mapping['dealerware_oem_metadata_user_attribute_default_value']])
            if len(mapping['dealerware_oem_metadata_oem_dealer_grp_name']) > 0:
                meta_groups.append(mapping['dealerware_oem_metadata_oem_dealer_grp_name'])

    # Obtain unique sets of attributes and groups.
    meta_attributes.sort()
    meta_attributes_deduped = list(attribute for attribute, _ in groupby(meta_attributes))
    meta_unique_attributes = {}
    for attribute_set in meta_attributes_deduped:
        attribute = attribute_set[0]
        meta_unique_attributes[attribute] = [attribute, attribute_set[1], attribute_set[2]]
    meta_unique_groups = set(meta_groups)

    for attribute in meta_unique_attributes.keys():
        if attribute not in attribute_id_details.keys():
            new_type = meta_unique_attributes[attribute][1]
            new_default = meta_unique_attributes[attribute][2]
            new_attribute_id = _create_missing_attribute(user_attribute_api, environment, attribute,
                                                         new_type, new_default)
            attribute_id_details[attribute] = [new_attribute_id, new_type, new_default]
    for group in meta_unique_groups:
        if group not in group_id_names.keys():
            new_group_id = _create_missing_group(group_api, environment, group)
            group_id_names[group] = new_group_id

    # Handle Edge Cases
    # Case 1: Handle for special attribute for first and last of month value updates.
    run_month_start_end_updates(user_attribute_api, attribute_id_details, group_id_names)
    # Add any additional edge case user attributes here which need custom attribute updates, for now only this one.

    # Get metadata mappings of each user attribute to group(s).
    metadata_attribute_group_mappings = defaultdict(list)
    for mapping in metadata_group_attributes:
        group_name = 'dealerware_oem_metadata_oem_dealer_grp_name'
        attribute_name = 'dealerware_oem_metadata_user_attribute_name'
        attribute_value = 'dealerware_oem_metadata_user_attribute_value'

        if len(mapping[url_field]) == 0 or len(mapping[group_name]) == 0:
            # Skip row that doesn't apply to current environment.
            continue

        metadata_attribute_name = mapping[attribute_name]
        meta_attribute_id = attribute_id_details[metadata_attribute_name][0]
        metadata_group = mapping[group_name]
        meta_group_id = group_id_names[metadata_group]
        metadata_attribute_value = mapping[attribute_value]

        metadata_attribute_group_mappings[meta_attribute_id].append({
            'attribute_name': metadata_attribute_name,
            'group_id': meta_group_id,
            'group_name': metadata_group,
            'attribute_value': metadata_attribute_value
        })
    metadata_attribute_group_dict = dict(metadata_attribute_group_mappings)

    # Get current mapping of user attributes to groups (potential future state)
    # user_attribute_group_mappings = defaultdict(list)
    # for attribute_name in attribute_id_details.keys():
    #     attribute_id = attribute_id_details[attribute_name][0]
    #     attribute_group_values = user_attribute_api_dev.all_user_attribute_group_values(attribute_id,
    #                                                                                     fields='group_id,'
    #                                                                                            'user_attribute_id,'
    #                                                                                            'value')
    #
    #     for attribute_dict in attribute_group_values:
    #         group_attribute_detail = {
    #             'attribute_name': attribute_name,
    #             'group_id': attribute_dict.group_id,
    #             'attribute_value': attribute_dict.value
    #         }
    #         # group_attributes_list = [attribute_dict.group_id for attribute_dict in attribute_group_values]
    #         user_attribute_group_mappings[attribute_id].append(group_attribute_detail)
    # user_attribute_group_dict = dict(user_attribute_group_mappings)

    # Compare attribute properties, update if necessary.
    for attribute_name, attribute_properties in meta_unique_attributes.items():
        if attribute_name in SPECIAL_CASE_ATTRIBUTES:
            # Special case attributes handled in separately, ignore as default behavior may not match special behavior.
            continue
        prior_type, prior_default = attribute_id_details[attribute_name][1], attribute_id_details[attribute_name][2]
        new_meta_type_value, new_meta_default = attribute_properties[1], attribute_properties[2]

        if prior_type != new_meta_type_value or prior_default != new_meta_default:
            if prior_type != new_meta_type_value:
                logger.info('Attribute {} has mismatched types, updating from {} to {} meta type in {}.'.format(
                    attribute_name, prior_type, new_meta_type_value, environment
                ))
            if prior_default != new_meta_default:
                logger.info('Attribute {} has mismatched defaults, updating from {} to {} meta default in {}.'.format(
                    attribute_name, prior_default, new_meta_default, environment
                ))
            _update_attribute_value(user_attribute_api, attribute_id_details[attribute_name][0],
                                    new_meta_type_value, new_meta_default)

    # Compare group user attribute values, update if necessary.
    for attribute_id, group_value_mapping in metadata_attribute_group_dict.items():
        group_values = []
        for mapping in group_value_mapping:
            group_values.append({'group_id': mapping['group_id'], 'value': mapping['attribute_value']})
        _set_new_group_attributes(user_attribute_api, attribute_id, group_values)


def authenticate_to_looker(host_base_url, token, secret) -> object:
    """Run Looker authentication and obtain client.

    :param host_base_url: String representing the URL for given Looker instance with the port and API version. For
     example - https://devdealerware.looker.com:19999/api/3.0
    :param token: Looker API user client ID
    :param secret: API user client secret.
    :return: Looker API client for given Looker instance.
    """
    unauthenticated_client = lookerapi.ApiClient(host_base_url)
    unauthenticated_auth_api = lookerapi.ApiAuthApi(unauthenticated_client)
    token = unauthenticated_auth_api.login(client_id=token, client_secret=secret)
    client = lookerapi.ApiClient(host_base_url, 'Authorization', 'token ' + token.access_token)

    return client


def get_metadata_table(client, look_id) -> list:
    """Return data from the OEM Dealer Group Master List metadata table saved Look.

    Execution runs as Text rather than JSON or CSV output. JSON is returned with single quotes and CSV returns with
    commas, each of which exist in data table, while text result is tab-delimited, which should not exist in metadata.

    :param client: API client for instance where metadata table resides.
    :param look_id: Int representing the ID of the metadata table's saved Look.
    :return: List of dictionaries representing rows of data from the Dealerware metadata table.
    """
    look_api = lookerapi.LookApi(client)

    # Extract Look output as text.
    metadata_table = look_api.run_look(look_id, result_format='txt', apply_formatting=False, apply_vis=False)
    table_rows = [row.split('\t') for row in metadata_table.strip().split('\n')]
    table_header = [column.lower().replace(' ', '_') for column in table_rows.pop(0)]

    metadata_group_attributes = []
    for row in table_rows:
        group_attribute_mapping = {}
        for column, value in zip(table_header, row):
            group_attribute_mapping[column] = value
        metadata_group_attributes.append(group_attribute_mapping)

    return metadata_group_attributes


def run_month_start_end_updates(attribute_api, attribute_mapping, group_mapping, month_start_field='first_of_month',
                                month_end_field='last_of_month', all_users_group='All Users'):
    """Update first and last of month user attributes if current month has changed and values for first and last of
    month user attributes still map to last month.

    :param attribute_api: Client for the Looker Attribute endpoint.
    :param attribute_mapping: Dict representing keys as string attribute names and values lists of [id, type, default].
    :param group_mapping: Dict representing keys as string group names and values as int group IDs.
    :param month_start_field: String User attribute name of the first of the month attribute.
    :param month_end_field: String User attribute name of the last of the month attribute.
    :param all_users_group: String representing the name of the default group all users are mapped to in Looker.
    :return: None.
    """
    first_day_current_month = datetime.today().date().replace(day=1)
    days_in_current_month = calendar.monthrange(datetime.now().year, datetime.now().month)[1]
    last_day_current_month = datetime.today().date().replace(day=days_in_current_month)

    if first_day_current_month == datetime.today().date():
        logging.info('Execution occurring on first day of month, attributes should be updated to current month.')

    month_start_attribute_id, start_type, start_default = attribute_mapping[month_start_field]
    month_end_attribute_id, end_type, end_default = attribute_mapping[month_end_field]
    all_user_group_id = group_mapping[all_users_group]

    month_start_update_body = {'default_value': first_day_current_month}
    month_end_update_body = {'default_value': last_day_current_month}
    month_start_group_values_body = {'group_id': all_user_group_id, 'value': first_day_current_month}
    month_end_group_values_body = {'group_id': all_user_group_id, 'value': last_day_current_month}

    attribute_api.update_user_attribute(month_start_attribute_id, body=month_start_update_body)
    attribute_api.update_user_attribute(month_end_attribute_id, body=month_end_update_body)

    attribute_api.set_user_attribute_group_values(month_start_attribute_id, body=[month_start_group_values_body])
    attribute_api.set_user_attribute_group_values(month_end_attribute_id, body=[month_end_group_values_body])


def _set_new_group_attributes(attribute_api, attribute_id, group_values_list):
    """Update group attribute values mapped to each user attribute.

    :param attribute_api: Client for the Looker Attribute endpoint.
    :param attribute_id: Dict with keys as int User Attribute IDs, and values as list of int group IDs.
    :param group_values_list: list of dicts representing all the int group IDs mapped to values for their attributes.
    :return: None.
    """
    logger.debug('Mapping group values {} to User Attribute {}'.format(str(group_values_list), attribute_id))
    group_attributes_body = group_values_list
    response = attribute_api.set_user_attribute_group_values(attribute_id, body=group_attributes_body)
    logger.debug('Response for attribute {}: {}.'.format(attribute_id, response))


def _update_attribute_value(attribute_api, attribute_id, attribute_type, default_value):
    """Update given Looker user attribute ID's default value to new given type and/or default.

    :param attribute_api: Client for the Looker Attribute endpoint.
    :param attribute_id: The User Attribute ID.
    :param default_value: String representing the new attribute type.
    :param default_value: Variant (matches attribute type) representing the new default value.
    :return: None.
    """
    new_body = {
        'type': attribute_type,
        'default_value': default_value
    }
    response = attribute_api.update_user_attribute(attribute_id, body=new_body)
    logger.debug(response)


def _create_missing_attribute(attribute_api, environment, new_attribute, new_type, new_default):
    """Create new attribute on current Looker instance.

    :param attribute_api: Client for the Looker Attribute endpoint.
    :param environment: String representing environment of execution, i.e. dev, prod.
    :param new_attribute: String representing the new attribute to be added (spaces not ok, use snake_case).
    :param new_type: String representing the type for the attribute.
    :param new_default: Variant representing the default for the attribute.
    :return: Int representing the ID of the newly created user attribute.
    """
    logger.warning('Missing attribute from metadata, adding attribute: {} in {}.'.format(new_attribute, environment))
    attribute_label = new_attribute.replace('_', ' ').title()
    new_attribute_body = {
        'name': new_attribute,
        'label': attribute_label,
        'type': new_type,
        'default_value': new_default,
        'value_is_hidden': False,
        'user_can_view': True,
        'user_can_edit': False
    }
    response = attribute_api.create_user_attribute(body=new_attribute_body)
    logger.debug(response)
    return response.id


def _create_missing_group(group_api, environment, new_group):
    """Create new group on current Looker instance.

    :param group_api: Client for the Looker Group endpoint.
    :param environment: String representing environment of execution, i.e. dev, prod.
    :param new_group: String representing Name of the new Looker group (spaces ok).
    :return: Int representing the ID of newly created Group.
    """
    logger.warning('Missing group from metadata, adding group: {} in {}.'.format(new_group, environment))
    new_group_body = {
        'name': new_group,
        'can_add_to_content_metadata': True
    }
    response = group_api.create_group(body=new_group_body)
    logger.debug(response)
    return response.id


if __name__ == '__main__':
    lambda_handler()
