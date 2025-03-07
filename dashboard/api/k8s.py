#! vim: ts=2 expandtab ai:

from kubernetes import client, config
from kubernetes.client.rest import ApiException

# TODO
#  Ensure your pod has a corresponding label, such as spec.template.metadata.labels.app: example-pod.

def create_notebook_pod(image,ns,id):
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
                    'name': f'jupyter-{id{',
                    'image': image
                }
            ]
        }
    }

    v1.create_namespaced_pod(namespace=ns, body=pod_manifest)
    # except ApiException as e:


# TODO
# ping example-service.krenek-ns.svc.cluster.local


def create_notebook_service(ns,id):
  config.load_kube_config()  # Or use config.load_incluster_config() if running inside a cluster
  
  # Define the service object
  service = client.V1Service(
      metadata=client.V1ObjectMeta(
          name=f'svc-{id}',
          namespace=id
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
  
  # Create the service in the specified namespace
  api_instance = client.CoreV1Api()
  api_response = api_instance.create_namespaced_service(
     namespace=ns,
     body=service
  )
 
#  except client.ApiException as e:
