// Tiny Go API. Breakproof reads this, never runs it.
package main

import "net/http"

func listUsers(w http.ResponseWriter, r *http.Request) {}
func createOrder(w http.ResponseWriter, r *http.Request) {}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/users", listUsers)
	mux.HandleFunc("/orders", createOrder)

	server := &http.Server{Addr: ":8080", Handler: mux}
	server.ListenAndServe()
}
