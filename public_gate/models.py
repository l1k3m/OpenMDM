import os
import plistlib
from plistlib import dumps
import uuid
import re

from django.contrib.auth.models import User
from mongoengine import *
from common.local.settings import CONFIG


class Plist(DynamicDocument):
    file_location = StringField(max_length=200)
    group_name = StringField(max_length=100)

    def __init__(self, recipe=None, *args, **values):
        super().__init__(*args, **values)
        if recipe is not None:
            self.display_name = recipe['display_name']
            self.version = recipe['recipe_version']

    def __str__(self):
        return "Plist " + str(self.display_name) + " for group " + str(self.group_name)

    def generate(self):
        """
        Generate an plist file from a PropertyList object
        """
        dictionary = self.to_mongo().to_dict()
        dictionary['_id'] = str(dictionary['_id'])
        result = {'payloadContent': dictionary}
        return dumps(result)


class RecipeForm():
    def __init__(self, recipe_name=None, data=None):
        self.recipe_path = os.path.normpath(os.path.dirname(__file__) + "/../recipe/") + "/" + recipe_name
        self.recipe_dict = plistlib.load(open(self.recipe_path, 'rb'), fmt=plistlib.FMT_XML)
        self.form_answer = {}
        self.plist = Plist(self.recipe_dict)
        # If form is filled out
        if data is not None:

            # We parse the expected outputs from the recipe
            for key, value in self.recipe_dict['outputs'].items():

                # And we fill an answer dictionary (in case of roll back)
                self.form_answer[key] = self.get_value_from_post_data(value, data)
                setattr(self.plist, key, self.get_value_from_post_data(value, data))

            # Then we add hook information
            self.plist.file_location = self.recipe_path
            self.plist.group_name = data.get("group_id")
            self.plist.uuid = str(uuid.uuid1()).upper()

    def get_value_from_post_data(self, value, data):
        # $key?(yes):(no)
        match = re.search("^\$(.*)\?\((.*)\):\((.*)\)$", value)
        if match:
            values = dict(key=match.group(1),
                          yes=match.group(2),
                          no=match.groups(3))
            if values['key'] in data:
                return self.get_value_from_post_data(values['yes'], data)
            else:
                return self.get_value_from_post_data(values['no'], data)

        # $key?(yes):
        match = re.search("^\$(.*)\?\((.*)\):$", value)
        if match:
            values = dict(key=match.group(1),
                          yes=match.group(2))
            if values['key'] in data:
                return self.get_value_from_post_data(values['yes'], data)
            return None

        # $key?:(no)
        match = re.search("^\$(.*)\?:\((.*)\)$", value)
        if match:
            values = dict(key=match.group(1),
                          no=match.group(2))
            if values['key'] not in data:
                return self.get_value_from_post_data(values['no'], data)
            return None

        # $key?
        match = re.search("^\$(.*)\?$", value)
        if match:
            values = dict(key=match.group(1))
            if values['key'] in data:
                return self.get_value_from_post_data("$" + values['key'], data)
            return None

        # $key
        match = re.search("^\$(.*)", value)
        if match:
            values = dict(key=match.group(1))
            if values['key'] in data:
                return data[values['key']]
            return None

        # @constant
        match = re.search("^@(.*)", value)
        if match:
            return match.group(1)

        # <hex>
        match = re.search("^<(.*)>$", value)
        if match:
            return match.group(1)

    def save(self):
        self.plist.save()

    @staticmethod
    def display_input(input_type, key, required, values, default_value, saved_value):
        """
        Creates HTML input, depending of the entry type
        :param input_type:
        :param key:
        :param required:
        :param values:
        :param default_value:
        :return string:
        """
        current_input = '<input type="{type}" ' \
                        'class="{input_class}" ' \
                        'name="{name}"' \
                        '{required}' \
                        '{checked} ' \
                        'value="{value}" ' \
                        'id="{id}">'
        if input_type == "string":
            current_input = current_input.format(id=key,
                                                 type="text",
                                                 input_class="form-control",
                                                 name=key,
                                                 required=" required" if required else "",
                                                 checked="",
                                                 value=saved_value if saved_value is not None
                                                 else default_value if default_value is not None
                                                 else "")
        if input_type == "boolean":
            current_input = current_input.format(id=key,
                                                 type="checkbox",
                                                 input_class="",
                                                 name=key,
                                                 required="",
                                                 checked=" checked" if saved_value is not None and saved_value
                                                 else "" if saved_value is not None and not saved_value
                                                 else " checked" if default_value
                                                 else "",
                                                 value="True")
        if input_type == "integer":
            current_input = current_input.format(id=key,
                                                 type="number",
                                                 input_class="form-control",
                                                 name=key,
                                                 required=" required" if required else "",
                                                 checked="",
                                                 value=saved_value if saved_value is not None
                                                 else default_value if default_value is not None
                                                 else "")
        if input_type == "list":
            select = []
            select.append('<select class="form-control" name="{name}"{required} id="{id}">'.format(name=key,
                                                                                             required=" required"
                                                                                             if required
                                                                                             else "",
                                                                                             id=key))
            for value in values:
                select.append('<option value="{value}"{selected}>'.format(value=value['value'],
                                                                     selected=" selected"
                                                                     if saved_value == value['value']
                                                                     else ""))

                select.append(value['title'])
                select.append("</option>")
            select.append('</select>')
            current_input = "\n".join(select)
        return current_input

    @staticmethod
    def check_key(obj, key):
        """
        Checks if key exists in dictionary, returns None if it doesn't
        :param obj:
        :param key:
        :return object:
        """
        return None if key not in obj.keys() else obj[key]

    @staticmethod
    def create_form(obj, form):
        """
        Create the html form from a python dictionary
        :param obj:
        :param form:
        :return string:
        """
        if type(obj).__name__ == "dict":
            if "type" in obj.keys():
                if obj['type'] == "group":
                    form.append('<fieldset><legend>{title}</legend>'.format(title=obj['title']))
                    form = RecipeForm.create_form(obj['content'], form)
                    form.append('</fieldset>')
                else:
                    form.append('<div class="form-group">')
                    label = '<label'
                    if obj['type'] != "boolean":
                        label += ' for="{id}"'.format(id=obj['key'])
                        label += '>{title}</label>'.format(title=obj['title'])
                    else:
                        label += '>'
                    form.append(label)

                    if RecipeForm.check_key(obj, "description") is not None:
                        form.append('<p class="help-block">{description}</p>'.format(description=obj['description']))
                    form.append(RecipeForm.display_input(input_type=obj['type'],
                                                     key=RecipeForm.check_key(obj, "key"),
                                                     required=RecipeForm.check_key(obj, "required"),
                                                     values=RecipeForm.check_key(obj, "values"),
                                                     default_value=RecipeForm.check_key(obj, "default_value"),
                                                     saved_value=None))
                    if obj['type'] == "boolean":
                        form.append(' {title}</label>'.format(title=obj['title']))
                    form.append('</div>')
            else:
                for key, value in obj.items():
                    if type(value).__name__ in ("dict", "list"):
                        form = RecipeForm.create_form(value, form)
        else:
            for value in obj:
                if type(value).__name__ in ("dict", "list"):
                    form = RecipeForm.create_form(value, form)
        return form

    def html_output(self):
        form = RecipeForm.create_form(self.recipe_dict, [])
        form.append('<div class="form-group">')
        form.append('<label for=group_id>Applies to group</label>')
        form.append('<select class="form-control" name="group_id" required id="group_id">')
        for group in CONFIG['local']['ldap']['GROUPS']:
            form.append('<option value="{value}">'.format(value=group))
            form.append(group)
            form.append("</option>")
        form.append('</select>')
        form.append('</div>')
        return "\n".join(form)