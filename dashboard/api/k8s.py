#! vim: ts=2 expandtab ai:

from kubernetes import client, config
from kubernetes.client.rest import ApiException

# TODO
#  Ensure your pod has a corresponding label, such as spec.template.metadata.labels.app: example-pod.

def create_notebook_pod(image,ns,id,prefix,token):
    # Load in-cluster config
    config.load_incluster_config()

    # Define API client
    v1 = client.CoreV1Api()

    # Define the pod specification
    pod_manifest = {
        'apiVersion': 'v1',
        'kind': 'Pod',
        'metadata': {
            'name': f'jupyter-{id}',
            'namespace': ns,
            'labels': {
              'app': f'jupyter-{id}'
            }
        },
        'spec': {
            'securityContext': {
                'runAsNonRoot' : True,
                'allowPrivilegeEscalation': False,
                'seccompProfile': {
                      'type': 'RuntimeDefault'
                    }
                },
            'containers': [
                {
                    'securityContext': {
                        'runAsNonRoot' : True,
                        'allowPrivilegeEscalation': False,
                        'capabilities':  {
                            'drop': [ 'ALL' ]
                            }
                        },
                    'name': f'jupyter-{id}',
                    'image': image,
#                    'env': [ {'name':'JUPYTERHUB_SERVICE_PREFIX', 'value':prefix } ],
                    'args': [
                      'start-notebook.sh',
                      f'--NotebookApp.base_url={prefix}',
                      f'--NotebookApp.notebook_dir=/mddash/{id}',
                      f'--NotebookApp.token="{token}"',
                    ],
                    'volumeMounts' : [
                      { 'mountPath': '/mddash', 'name' : 'data-volume' }
                    ]
                }
            ],
            'volumes': [ 
              { 'name': 'data-volume',
                'persistentVolumeClaim': { 'claimName' : 'mddash-data' }
              }
            ]
        }
    }

    v1.create_namespaced_pod(namespace=ns, body=pod_manifest)
    # except ApiException as e:


# TODO
# ping example-service.krenek-ns.svc.cluster.local



def delete_notebook_pod(ns,id):
  config.load_incluster_config()
  api = client.CoreV1Api()

  api.delete_namespaced_pod(name='jupyter-'+id, namespace=ns)

def delete_notebook_service(ns,id):
  config.load_incluster_config()
  api = client.CoreV1Api()

  api.delete_namespaced_service(name='svc-'+id, namespace=ns)

def create_notebook_service(ns,id):
  config.load_incluster_config()
  
  service = client.V1Service(
      metadata=client.V1ObjectMeta(
          name=f'svc-{id}',
          namespace=ns
      ),
      spec=client.V1ServiceSpec(
          selector={"app": f"jupyter-{id}"},  
          ports=[client.V1ServicePort(
              protocol="TCP",
              port=80,  
              target_port=8888  
          )]
      )
  )
  
  api_instance = client.CoreV1Api()
  api_response = api_instance.create_namespaced_service(
     namespace=ns,
     body=service
  )
 
#  except client.ApiException as e:
