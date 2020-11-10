# --
# File: archer_views.py
#
# Copyright (c) 2016-2020 Splunk Inc.
#
# SPLUNK CONFIDENTIAL - Use or disclosure of this material in whole or in part
# without a valid written license from Splunk Inc. is PROHIBITED.
#
# --


def get_ticket(provides, all_results, context):

    context['results'] = results = []
    for summary, action_results in all_results:
        for result in action_results:
            parameters = result.get_param()
            if 'context' in parameters:
                del parameters['context']
            rec = {'parameters': parameters}
            data = result.get_data()
            if data:
                data = data[0]['Record']['Field']
            rec['record'] = sorted(data, key=lambda x: (x['@name'] is not None, x['@name']))
            rec['content_id'] = result.get_summary().get(
                'content_id', 'Not provided')
            results.append(rec)

    return 'get_ticket.html'


def list_tickets(provides, all_results, context):

    headers = ['application', 'content id']
    context['results'] = results = []

    headers_set = set()
    for summary, action_results in all_results:
        for result in action_results:
            for record in result.get_data():
                headers_set.update([f.get('@name', '').strip()
                                    for f in record.get('Field', [])])
    if not headers_set:
        headers_set.update(headers)
    headers.extend(sorted(headers_set))

    final_result = {'headers': headers, 'data': []}

    dyn_headers = headers[2:]
    for summary, action_results in all_results:
        for result in action_results:
            data = result.get_data()
            param = result.get_param()
            for item in data:
                row = []
                row.append({'value': param.get('application'),
                            'contains': ['archer application']})
                row.append({'value': item.get('@contentId'),
                            'contains': ['archer content id']})
                name_value = {}
                for f in item.get('Field', []):
                    name_value[f['@name']] = f.get('#text')

                for h in dyn_headers:
                    if h == 'IP Address':
                        row.append({'value': name_value.get(h, ''),
                                    'contains': ['ip']})
                    else:
                        row.append({'value': name_value.get(h, '')})
                final_result['data'].append(row)

    results.append(final_result)
    return 'list_tickets.html'
