def retrieve(store, question, k):
    return store.as_retriever(search_kwargs={'k': k}).invoke(question)
