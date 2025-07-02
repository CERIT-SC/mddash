from kubernetes import client, config
from kubernetes.client.rest import ApiException

# TODO
#  Ensure your pod has a corresponding label, such as spec.template.metadata.labels.app: example-pod.

# XXX: hardcoded gromacs image

def create_notebook_pod(image, ns, id, prefix, token):
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
                        'runAsUser': 1000,
                        'allowPrivilegeEscalation': False,
                        'capabilities':  {
                            'drop': [ 'ALL' ]
                        }
                    },
                    'name': f'jupyter',
                    'image': image,
                    'imagePullPolicy': 'Always',
                    'resources': {
                        'requests' : { 'cpu': .1, 'memory': '2Gi' }, 
                        'limits' : { 'cpu': 2, 'memory' : '8Gi' }
                    },
                    'workdir': f'/mddash/{id}',
                    'args': [
                        'start-notebook.sh',
                        f'--NotebookApp.base_url={prefix}',
                        f'--NotebookApp.notebook_dir=/mddash/{id}',
                        f'--NotebookApp.token="{token}"',
                    ],
                    'volumeMounts' : [
                        { 'mountPath': '/mddash', 'name' : 'data-volume' }
                    ]
                },
                {
                    'securityContext': {
                        'runAsNonRoot' : True,
                        'runAsUser': 1000,
                        'allowPrivilegeEscalation': False,
                        'capabilities':  {
                            'drop': [ 'ALL' ]
                        }
                    },
                    'name': f'gmx',
                    'image': 'cerit.io/ljocha/gromacs:2024-3-plumed-2-10-afed-pytorch-model-cv-2',
                    'imagePullPolicy': 'Always',
                    'resources': {
                        'requests' : { 'cpu': .1, 'memory': '2Gi' }, 
                        'limits' : { 'cpu': 2, 'memory' : '8Gi' }
                    },
                    'workdir': f'/mddash/{id}',
                    'args': [
                        'sleep',
                        '365d'
                    ],
                    'volumeMounts' : [
                        { 'mountPath': '/mddash', 'name' : 'data-volume' }
                    ]
                }
            ],
            'volumes': [ 
                {
                    'name': 'data-volume',
                    'persistentVolumeClaim': { 'claimName' : 'mddash-data' }
                }
            ]
        }
    }

    v1.create_namespaced_pod(namespace=ns, body=pod_manifest)
    # except ApiException as e:


def ping_resource(resource_type, name, ns):
    config.load_incluster_config()
    api = client.CoreV1Api()

    try:
        match resource_type:
            case 'svc':
                api.read_namespaced_service(name=name, namespace=ns)
            case 'pod':
                api.read_namespaced_pod(name=name, namespace=ns)
            case 'configmap':
                api.read_namespaced_config_map(name=name, namespace=ns)
            case 'secret':
                api.read_namespaced_secret(name=name, namespace=ns)
            case 'pvc':
                api.read_namespaced_persistent_volume_claim(name=name, namespace=ns)
            case _:
                raise ValueError(f"Unsupported resource type: {resource_type}")
        return True
    except ApiException as e:
        return False


def delete_notebook_pod(ns, id):
    if not ping_resource('pod', f'jupyter-{id}', ns):
        return

    config.load_incluster_config()
    api = client.CoreV1Api()
    api.delete_namespaced_pod(name='jupyter-'+id, namespace=ns)


def delete_notebook_service(ns, id):
    if not ping_resource('svc', f'svc-{id}', ns):
        return

    config.load_incluster_config()
    api = client.CoreV1Api()
    api.delete_namespaced_service(name='svc-'+id, namespace=ns)


def create_notebook_service(ns, id):
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


def get_namespace_resource_allocation(ns):
    '''
    Get resource requests/limits for all pods in namespace

    NOTE: This is just a proof-of-concept version, later we will need some metrics server like Prometheus.
    '''
    config.load_incluster_config()
    api = client.CoreV1Api()
    
    try:
        pods = api.list_namespaced_pod(namespace=ns)
        total_cpu_requests = 0
        total_memory_requests = 0
        
        for pod in pods.items:
            for container in pod.spec.containers:
                if container.resources and container.resources.requests:
                    # Parse CPU requests
                    if 'cpu' in container.resources.requests:
                        cpu_str = container.resources.requests['cpu']
                        if cpu_str.endswith('m'):
                            total_cpu_requests += int(cpu_str[:-1]) / 1000
                        else:
                            total_cpu_requests += float(cpu_str)
                    
                    # Parse memory requests  
                    if 'memory' in container.resources.requests:
                        mem_str = container.resources.requests['memory']
                        if mem_str.endswith('Gi'):
                            total_memory_requests += float(mem_str[:-2])
                        elif mem_str.endswith('Mi'):
                            total_memory_requests += float(mem_str[:-2]) / 1024
        
        return {
            'cpu': round(total_cpu_requests, 3),
            'memory': round(total_memory_requests, 2),
            'gpu': 0
        }
    except Exception as e:
        print(f"Error: {e}")
        return {'cpu': 0, 'memory': 0, 'gpu': 0}
