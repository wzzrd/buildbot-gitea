import json
import re
from buildbot.util import bytes2unicode
from buildbot.www.hooks.base import BaseHookHandler

from twisted.python import log
from dateutil.parser import parse as dateparse

_HEADER_EVENT_TYPE = 'X-Gitea-Event'


class GiteaHandler(BaseHookHandler):

    def processPushEvent(self, payload, event_type, codebase):
        refname = payload["ref"]

        changes = []

        # We only care about regular heads or tags
        match = re.match(r"^refs/(heads|tags)/(.+)$", refname)
        if not match:
            log.msg("Ignoring refname '{}': Not a branch or tag".format(refname))
            return changes

        branch = match.group(2)

        repository = payload['repository']
        repo_url = repository['ssh_url']
        project = repository['full_name']

        for commit in payload['commits']:
            timestamp = dateparse(commit['timestamp'])
            change = {
                'author': '{} <{}>'.format(commit['author']['name'],
                                           commit['author']['email']),
                'comments': commit['message'],
                'revision': commit['id'],
                'when_timestamp': timestamp,
                'branch': branch,
                'revlink': commit['url'],
                'repository': repo_url,
                'project': project,
                'category': event_type,
                'properties': {
                    'event': event_type,
                },
            }
            if codebase is not None:
                change['codebase'] = codebase
            changes.append(change)
        return changes

    def processPullRequestEvent(self, payload, event_type, codebase):
        action = payload['action']

        # Only handle potential new stuff, ignore close/.
        # Merge itself is handled by the regular branch push message
        if action not in ['opened', 'synchronized', 'edited', 'reopened']:
            log.msg("Gitea Pull Request event '{}' ignored".format(action))
            return []
        pull_request = payload['pull_request']
        timestamp = dateparse(pull_request['updated_at'])
        base = pull_request['base']
        head = pull_request['head']
        repository = payload['repository']
        change = {
            'author': '{} <{}>'.format(pull_request['user']['full_name'],
                                       pull_request['user']['email']),
            'comments': 'PR#{}: {}\n\n{}'.format(
                pull_request['number'],
                pull_request['title'],
                pull_request['body']),
            'revision': pull_request['merge_base'],
            'when_timestamp': timestamp,
            'branch': head['ref'],
            'revlink': pull_request['html_url'],
            'repository': repository['ssh_url'],
            'project': repository['full_name'],
            'category': event_type,
            'properties': {
                'event': event_type,
                'base_branch': base['ref'],
                'base_sha': base['sha'],
                'base_repo_id': base['repo_id'],
                'base_repository': base['repo']['clone_url'],
                'base_git_ssh_url': base['repo']['ssh_url'],
                'head_branch': head['ref'],
                'head_sha': head['sha'],
                'head_repo_id': head['repo_id'],
                'head_repository': head['repo']['clone_url'],
                'head_git_ssh_url': head['repo']['ssh_url'],
                'pr_id': pull_request['id'],
                'pr_number': pull_request['number'],
            },
        }
        if codebase is not None:
            change['codebase'] = codebase
        return [change]

    def getChanges(self, request):
        secret = None
        if isinstance(self.options, dict):
            secret = self.options.get('secret')

        try:
            content = request.content.read()
            payload = json.loads(bytes2unicode(content))
        except Exception as e:
            raise ValueError('Error loading JSON: ' + str(e))
        if secret is not None and secret != payload['secret']:
            raise ValueError('Invalid secret')

        event_type = bytes2unicode(request.getHeader(_HEADER_EVENT_TYPE))
        log.msg("Received event '{}' from gitea".format(event_type))

        codebases = request.args.get('codebase', [None])
        codebase = bytes2unicode(codebases[0])
        changes = []
        if event_type == 'push':
            changes = self.processPushEvent(
                payload, event_type, codebase)
        elif event_type == 'pull_request':
            changes = self.processPullRequestEvent(
                payload, event_type, codebase)
        else:
            log.msg("Ignoring gitea event '{}'".format(event_type))

        return (changes, 'git')


# Plugin name
gitea = GiteaHandler
