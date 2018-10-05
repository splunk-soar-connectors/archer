# --
# File: ./archer/archer_views.py
#
# Copyright (c) Phantom Cyber Corporation, 2014-2018
#
# This unpublished material is proprietary to Phantom Cyber.
# All rights reserved. The methods and
# techniques described herein are considered trade secrets
# and/or confidential. Reproduction or distribution, in whole
# or in part, is forbidden except by express written permission
# of Phantom Cyber.
#
# --

from django.http import HttpResponse
import json


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
            rec['record'] = sorted(data, key=lambda x: x['@name'])
            rec['content_id'] = result.get_summary().get(
                'content_id', 'Not provided')
            results.append(rec)

    return 'get_ticket.html'


def list_tickets(provides, all_results, context):

    headers = ['application', 'content id']

    headers_set = set()
    for summary, action_results in all_results:
        for result in action_results:
            for record in result.get_data():
                headers_set.update([f.get('@name', '').strip()
                                    for f in record.get('Field', [])])
    if not headers_set:
        headers_set.update(headers)
    headers.extend(sorted(headers_set))

    context['ajax'] = True
    if 'start' not in context['QS']:
        context['headers'] = headers
        return '/widgets/generic_table.html'

    start = int(context['QS']['start'][0])
    length = int(context['QS'].get('length', ['5'])[0])
    end = start + length
    rows = []
    total = 0
    dyn_headers = headers[2:]
    for summary, action_results in all_results:
        for result in action_results:
            data = result.get_data()
            param = result.get_param()
            total += len(data)
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
                rows.append(row)

    content = {
        "data": rows[start:end],
        "recordsTotal": total,
        "recordsFiltered": total,
    }
    return HttpResponse(json.dumps(content), content_type='text/javascript')
