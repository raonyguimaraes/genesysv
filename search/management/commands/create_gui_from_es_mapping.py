from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from search.models import *
from search.models import *
import elasticsearch
import json
from pprint import pprint
import re
from natsort import natsorted

def get_from_es(dataset_es_index_name,
                dataset_es_type_name,
                dataset_es_host,
                dataset_es_port,
                field_es_name,
                field_path):


    es = elasticsearch.Elasticsearch(host=dataset_es_host, port=dataset_es_port)

    if not field_path:
        body_non_nested_template = """
            {
                "size": 0,
                "aggs" : {
                    "values" : {
                        "terms" : { "field" : "%s", "size" : 1000 }
                    }
                }
            }
        """
        body = body_non_nested_template %(field_es_name)
        results = es.search(index=dataset_es_index_name,
                            doc_type=dataset_es_type_name,
                            body=body)
        return natsorted([ele['key'] for ele in results["aggregations"]["values"]["buckets"]])


    elif field_path:
        body_nested_template = """
            {
                "size": 0,
                "aggs" : {
                    "values" : {
                        "nested" : {
                            "path" : "%s"
                        },
                        "aggs" : {
                            "values" : {"terms" : {"field" : "%s.%s", "size" : 1000}}
                        }
                    }
                }
            }
        """
        body = body_nested_template %(field_path,
                                      field_path,
                                      field_es_name)


        results = es.search(index=dataset_es_index_name,
                            doc_type=dataset_es_type_name,
                            body=body)
        return natsorted([ele['key'] for ele in results["aggregations"]["values"]["values"]["buckets"]])


def fetch_data_type_from_es(dataset_es_index_name,
                            dataset_es_type_name,
                            dataset_es_host,
                            dataset_es_port,
                            field_es_name,
                            field_path):

    es = elasticsearch.Elasticsearch(host=dataset_es_host, port=dataset_es_port)
    mapping = es.indices.get_mapping(index=dataset_es_index_name, doc_type=dataset_es_type_name)

    if field_path:
        try:
            return mapping[dataset_es_index_name]['mappings'][dataset_es_type_name]['properties'][field_path]['properties'][field_es_name]['type']
        except KeyError as e:
            raise KeyError(e)
    else:
        try:
            return mapping[dataset_es_index_name]['mappings'][dataset_es_type_name]['properties'][field_es_name]['type']
        except KeyError as e:
            raise(e)




class Command(BaseCommand):


    def add_arguments(self, parser):
        required = parser.add_argument_group('required named arguments')
        required.add_argument("--hostname", help="Elasticsearch hostname", required=True)
        required.add_argument("--port", type=int, help="Elasticsearch port", required=True)
        required.add_argument("--index", help="Elasticsearch index name", required=True)
        required.add_argument("--type", help="Elasticsearch doc type name", required=True)
        required.add_argument("--labels", help="Cohort labels, e.g., \"control, case\" or \"None\"", required=True)
        required.add_argument("--study", help="Study name", required=True)
        required.add_argument("--dataset", help="Dataset name", required=True)


    def handle(self, *args, **options):

        hostname = options.get('hostname')
        port = options.get('port')
        index_name = options.get('index')
        study = options.get('study')
        dataset = options.get('dataset')
        type_name = options.get('type')



        es = elasticsearch.Elasticsearch(host=hostname, port=port)

        mapping = elasticsearch.client.IndicesClient.get_mapping(es, index=index_name, doc_type=type_name)
        # mapping = mapping[options.get('study]')['mappings'][options.get('dataset]['properties']
        mapping = mapping[study]['mappings'][dataset]['properties']



        nested_fields = []
        for var_name, var_info in mapping.items():
            if var_info.get('type') == 'nested':
                nested_fields.append(var_name)

        popped_nested_fields = {}
        for ele in nested_fields:
            popped_nested_fields[ele] = mapping.pop(ele)

        for key, value in popped_nested_fields.items():
            for inner_key, inner_value in value['properties'].items():
                mapping[inner_key] = inner_value




        vcf_gui_mapping = json.load(open('search/management/commands/data/vcf_field_gui_mapping.json', 'r'))


        print("*"*80+"\n")
        print('Study Name: %s' %(study))
        print('Dataset Name: %s' %(dataset))
        print('Dataset ES Index Name: %s' %(index_name))
        print('Dataset ES Type Name: %s' %(type_name))
        print('Dataset ES Host: %s' %(hostname))
        print('Dataset ES Port: %s' %(port))


        ### Verify Study against Django models
        study_obj, created = Study.objects.get_or_create(name=study, description=study)

        ### Verify Dataset against Django models
        dataset_obj, created = Dataset.objects.get_or_create(study=study_obj,
                                name=dataset,
                                description=dataset,
                                es_index_name=index_name,
                                es_type_name=type_name,
                                es_host=hostname,
                                es_port=port,
                                is_public=True)

        SearchOptions.objects.get_or_create(dataset=dataset_obj)




        idx = 1
        for var_name, var_info in mapping.items():
            if var_info.get('type') == 'nested':
                print('*'*20, 'ERROR', var_name)
                continue
            if not vcf_gui_mapping.get(var_name):
                print('*'*20, 'ERROR', var_name)
                continue

            gui_info = vcf_gui_mapping.get(var_name)

            tab_name = gui_info.get('tab')
            panel_name = gui_info.get('panel')
            sub_panel_name = gui_info.get('sub_panel')
            filters = gui_info.get('filters')


            for filter_field in filters:

                field_display_text = filter_field.get('display_text')
                field_tooltip = filter_field.get('tooltip', '')
                field_in_line_tooltip = filter_field.get('in_line_tooltip', '')
                field_form_type = filter_field.get('form_type')
                field_widget_type = filter_field.get('widget_type')
                field_es_name = var_name
                field_es_filter_type = filter_field.get('es_filter_type')
                field_es_data_type = var_info.get('type')
                field_path = filter_field.get('path', '')
                field_values = filter_field.get('values')


                # print("\n%s --- Filter Field" %(idx))
                # print("Filter Tab Name: %s" %(tab_name))
                # print("Filter Panel Name: %s" %(panel_name))
                # print("Filter Subpanel Name: %s" %(sub_panel_name))
                # print("Filter Display Name: %s" %(field_display_text))
                # print("Filter in Line Tooltip: %s" %(field_in_line_tooltip))
                # print("Filter Tooltip: %s" %(field_tooltip))
                # print("Filter Form Type: %s" %(field_form_type))
                # print("Filter Widget Type: %s" %(field_widget_type))
                # print("Filter ES Name: %s" %(field_es_name))
                # print("Filter Path: %s" %(field_path))
                # print("Filter ES Filter Type: %s" %(field_es_filter_type))
                # print("Filter ES Data Type: %s" %(field_es_data_type))
                # print("Filter Values: %s" %(field_values))


                match_status = False
                if isinstance(field_values, str):
                    match = re.search(r'python_eval(.+)', field_values)
                    if field_values == 'get_from_es()':
                        field_values = get_from_es(index_name,
                                            type_name,
                                            hostname,
                                            port,
                                            field_es_name,
                                            field_path)
                    elif match:
                        match_status = True
                        tmp_str = match.groups()[0]
                        try:
                            field_values = eval(tmp_str)
                        except NameError as e:
                            print('Failed to evaluate %s' %(tmp_str))
                            raise(e)



                form_type_obj = FormType.objects.get(name=field_form_type)
                widget_type_obj = WidgetType.objects.get(name=field_widget_type)
                es_filter_type_obj = ESFilterType.objects.get(name=field_es_filter_type)


                filter_tab_obj, _ = FilterTab.objects.get_or_create(dataset=dataset_obj, name=tab_name)
                filter_panel_obj, _ = FilterPanel.objects.get_or_create(name=panel_name)


                if not filter_tab_obj.filter_panels.filter(id=filter_panel_obj.id):
                        filter_tab_obj.filter_panels.add(filter_panel_obj)



                filter_field_obj, created = FilterField.objects.get_or_create(dataset=dataset_obj,
                                                               display_text=field_display_text,
                                                               in_line_tooltip=field_in_line_tooltip,
                                                               tooltip=field_tooltip,
                                                               form_type=form_type_obj,
                                                               widget_type=widget_type_obj,
                                                               es_name=field_es_name,
                                                               path=field_path,
                                                               es_data_type=field_es_data_type,
                                                               es_filter_type=es_filter_type_obj)


                if field_values:
                    for choice in field_values:
                        FilterFieldChoice.objects.get_or_create(filter_field=filter_field_obj, value=choice)



                attribute_tab_obj, _ = AttributeTab.objects.get_or_create(dataset=dataset_obj, name=tab_name)
                attribute_panel_obj, _ = AttributePanel.objects.get_or_create(name=panel_name)

                if not attribute_tab_obj.attribute_panels.filter(id=attribute_panel_obj.id):
                        attribute_tab_obj.attribute_panels.add(attribute_panel_obj)

                try:
                    attribute_field_obj, created = AttributeField.objects.get_or_create(dataset=dataset_obj,
                                                           display_text=field_display_text,
                                                           es_name=field_es_name,
                                                           path=field_path)
                except:
                    pass

                if sub_panel_name:
                    filter_sub_panel_obj, _ = FilterSubPanel.objects.get_or_create(filter_panel=filter_panel_obj,
                                                                 name=sub_panel_name)

                    attribute_sub_panel_obj, _ = AttributeSubPanel.objects.get_or_create(attribute_panel=attribute_panel_obj,
                                                             name=sub_panel_name)

                    if not filter_sub_panel_obj.filter_fields.filter(id=filter_field_obj.id):
                        filter_sub_panel_obj.filter_fields.add(filter_field_obj)



                    attribute_field_obj, created = AttributeField.objects.get_or_create(dataset=dataset_obj,
                                                               display_text=field_display_text,
                                                               es_name=field_es_name,
                                                               path=field_path)

                    if not attribute_sub_panel_obj.attribute_fields.filter(id=attribute_field_obj.id):
                        attribute_sub_panel_obj.attribute_fields.add(attribute_field_obj)

                else:

                    if not filter_panel_obj.filter_fields.filter(id=filter_field_obj.id):
                        filter_panel_obj.filter_fields.add(filter_field_obj)



                    if not attribute_panel_obj.attribute_fields.filter(id=attribute_field_obj.id):
                        attribute_panel_obj.attribute_fields.add(attribute_field_obj)
                idx += 1