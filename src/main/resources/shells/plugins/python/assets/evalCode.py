def run(ctx):
    namespace = {}
    exec(ctx.get('plugin_eval_code'), namespace)
    return namespace.get('result', None)