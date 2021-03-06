import os
import inspect
import importlib
import pkgutil
import types
import random
from hpit.plugins.problem_generator import problems

from hpitclient import Plugin

from hpit.management.settings_manager import SettingsManager
settings = SettingsManager.get_plugin_settings()

class ProblemGeneratorPlugin(Plugin):

    def __init__(self, entity_id, api_key, logger, args = None):
        self.logger = logger
        self.load_problem_library()
        super().__init__(entity_id, api_key)


    def load_problem_library(self):
        self.problem_library = {}
        root_directory = os.path.dirname(problems.__file__)

        for dirpath, dirnames, filenames in os.walk(root_directory):
            if dirpath.endswith('__pycache__'):
                continue

            filenames = [fn for fn in filenames if fn != '__init__.py']

            if not filenames:
                continue

            for fn in filenames:
                import_path = dirpath.replace(settings.PROJECT_DIR, '')[1:].split(os.sep)

                category_name = fn.split('.')[0]
                subject_name = import_path[-1]
                import_path.append(category_name)

                if not category_name:
                    continue
                    
                imported = importlib.import_module('.'.join(import_path))

                functions = {}
                for attr in dir(imported):
                    if attr.endswith('Problem'):
                        cls_inst = getattr(imported, attr, None)()
                        if cls_inst.problem_enabled:
                            functions[attr] = cls_inst

                if functions:
                    if subject_name not in self.problem_library:
                        self.problem_library[subject_name] = {}

                    subject_dict = self.problem_library[subject_name]
                    subject_dict[category_name] = functions

        self.update_problem_list()


    def update_problem_list(self):
        self.problem_list = {
            subjects: {category: list(skills.keys()) for category, skills in categories.items()}
        for subjects, categories in self.problem_library.items() }


    def generate_problem(self, subject=None, category=None, skill=None, **kwargs):
        if subject is None:
            subject = random.choice(list(self.problem_library.keys()))
        elif subject not in self.problem_library:
            raise Exception("Subject is invalid.")

        subject_obj = self.problem_library[subject]

        if category is None:
            category = random.choice(list(subject_obj.keys()))
        elif category not in subject_obj:
            raise Exception("Category is invalid.")

        category_obj = subject_obj[category]

        if skill is None:
            skill = random.choice(list(category_obj.keys()))
        elif skill not in category_obj:
            raise Exception("Skill is invalid.")

        skill_obj = category_obj[skill]

        problem_text, answer_text = skill_obj(**kwargs)

        return {
            'subject': subject,
            'category': category,
            'skill': skill,
            'problem_text': problem_text,
            'answer_text': answer_text
        }


    def post_connect(self):
        super().post_connect()

        self.subscribe({
            "tutorgen.pg_list_problems":self.list_problems_callback,
            "tutorgen.pg_generate_problem":self.generate_problem_callback
        })


    def list_problems_callback(self, message):
        if 'subject' not in message:
            self.send_response(message['message_id'], self.problem_list)
            return True

        subject = message['subject']
        if subject not in self.problem_list:
            self.send_response(message['message_id'], {
                'error': "Subject <" + subject + "> does not exist.",
                'send': {
                    'subjects': list(self.problem_list.keys())
                }
            })
            return False

        categories = self.problem_list[subject]
        if 'category' not in message:
            self.send_response(message['message_id'], {
                subject: categories
            })
            return True

        category = message['category']
        if category not in categories:
            self.send_response(message['message_id'], {
                'error': "Category <" + category + "> does not exist in subject <" + subject + ">",
                'send': {
                    'categories': list(categories.keys())
                }
            })
            return False

        skills = categories[category]
        if 'skill' not in message:
            self.send_response(message['message_id'], {
                subject: { 
                    category: skills 
                }
            })
            return True

        skill = message['skill']
        if skill not in skills:
            self.send_response(message['message_id'], {
                'error': 'Skill <' + skill + "> does not exist in subject <" + subject + "> and category <" + category + ">",
                'send': {
                    'skills': skills
                }
            })
            return False

        self.send_response(message['message_id'], {
            subject: { 
                category: skills 
            }
        })

        return True


    def generate_problem_callback(self, message):
        subject = message['subject'] if 'subject' in message else None
        category = message['category'] if 'category' in message else None
        skill = message['skill'] if 'skill' in message else None
        count = message['count'] if 'count' in message else 1
        options = message['options'] if 'options' in message else {}

        problems = []
        try:
            for i in range(0, count):
                problems.append(self.generate_problem(subject, category, skill, **options))
        except Exception as e:
            self.send_response(message['message_id'], {
                'error': str(e),
                'you_sent': {
                    'subject': subject,
                    'category': category,
                    'skill': skill,
                    'count': count,
                    'options': options
                }
            })
            return False

        self.send_response(message['message_id'], {
            'problems': problems
        })
        return True

