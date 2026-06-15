package main

import (
	"encoding/json"
	"log"
	"net/http"
)

func pingHandler(w http.ResponseWriter, r *http.Request) {
	response := map[string]interface{}{
		"code":    200,
		"message": "pong",
	}
	
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(response)
}

func main() {
	http.HandleFunc("/ping", pingHandler)
	
	log.Println("HTTP server starting on :8080...")
	if err := http.ListenAndServe(":8080", nil); err != nil {
		log.Printf("服务器启动失败: %v", err)
	}
}